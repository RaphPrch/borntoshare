from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.api import access_requests as access_requests_routes
from app.api import provisioning_internal
from app.core.direct_call import call_route
from app.api._helpers import ui_data
from app.schemas.provisioning import RemoveAdGroupMemberIn
from app.api.governance.provisioning import (
    ProvisioningStepError,
    queue_ad_access_grant,
    remove_ad_group_member,
    wait_provisioning_job,
)
from app.services.audit_logger import log_event
from app.services.probe_service import fetch_probe_job, submit_acl_propagation, submit_probe_run
from app.core.values import unwrap_data


router = APIRouter(prefix="/access-requests", tags=["access-requests"])


def _normalize_ids(raw: Any) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    if not isinstance(raw, list):
        return out
    for value in raw:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in seen:
            seen.add(parsed)
            out.append(parsed)
    return out


def _normalize_failed_detail(raw: Any) -> dict[str, Any]:
    detail = dict(raw or {}) if isinstance(raw, dict) else {}
    item_id = detail.get("item_id")
    storage_root_id = detail.get("storage_root_id")
    requested_permission = str(detail.get("requested_permission") or "").strip().upper() or None
    repair_result = str(detail.get("repair_result") or "").strip() or None

    def _to_int_or_none(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    return {
        "item_id": _to_int_or_none(item_id),
        "code": str(detail.get("code") or "APPROVAL_FAILED").strip() or "APPROVAL_FAILED",
        "message": str(detail.get("message") or "Approval failed").strip() or "Approval failed",
        "hint": str(detail.get("hint") or "Resolve item-level errors and retry approval.").strip()
        or "Resolve item-level errors and retry approval.",
        "storage_root_id": _to_int_or_none(storage_root_id),
        "requested_permission": requested_permission,
        "candidates_count": int(detail.get("candidates_count") or 0),
        "repair_attempted": bool(detail.get("repair_attempted") or False),
        "repair_result": repair_result,
        # AD group conflict: the existing group a platform admin can adopt
        "access_profile_id": _to_int_or_none(detail.get("access_profile_id")),
        "group_name": str(detail.get("group_name") or "").strip() or None,
        "existing_dn": str(detail.get("existing_dn") or "").strip() or None,
        "job_id": _to_int_or_none(detail.get("job_id")),
    }


def _request_with_id(request: Request, request_id: str) -> Request:
    class _ReqProxy:
        def __init__(self, base: Request, rid: str) -> None:
            self._base = base
            self.headers = dict(getattr(base, "headers", {}) or {})
            self.headers["x-request-id"] = str(rid)

        def __getattr__(self, name: str):
            return getattr(self._base, name)

    return _ReqProxy(request, request_id)  # type: ignore[return-value]


# Waiting times of the approval call (the capsule retries network errors within them)
GRANT_TIMEOUT_SEC = 90
ACL_TIMEOUT_SEC = 60
REVOKE_TIMEOUT_SEC = 60


def _journal(
    action: str,
    *,
    req_id: int,
    request: Request,
    correlation_id: str,
    storage_root_id: int | None = None,
    result: str = "success",
    severity: str = "info",
    **details: Any,
) -> None:
    """One entry of the provisioning log of an access request (activity log, filtered by request)."""
    actor_id = str(request.headers.get("x-identity-id") or "").strip() or None
    log_event(
        action=action,
        event_category="PROVISIONING",
        actor_type="user" if actor_id and actor_id.isdigit() else "service",
        actor_id=actor_id or "system",
        entity_type="access_request",
        entity_id=int(req_id),
        storage_root_id=int(storage_root_id or 0) or None,
        correlation_id=correlation_id,
        result=result,
        severity=severity,
        metadata_json={k: v for k, v in details.items() if v is not None},
    )


def _job_failure(job: dict[str, Any], *, job_id: int, step: str) -> ProvisioningStepError:
    result = dict(job.get("result_json") or {}) if isinstance(job.get("result_json"), dict) else {}
    details = dict(result.get("details") or {}) if isinstance(result.get("details"), dict) else {}
    return ProvisioningStepError(
        str(job.get("error_code") or details.get("failure_code") or f"{step.upper()}_FAILED"),
        str(job.get("error_message") or result.get("message") or f"{step} failed"),
        job_id=job_id,
        **{k: details.get(k) for k in ("existing_dn", "group_name", "target_ou_dn", "directory_server") if details.get(k)},
    )


async def _grant_item(
    *,
    req_id: int,
    item: dict[str, Any],
    principal_dn: str | None,
    principal_username: str | None,
    request: Request,
    correlation_id: str,
) -> dict[str, Any]:
    """AD group (found, adopted or created at the first approval) + membership + NTFS ACL, in this order.

    Each step waits for the previous one and writes its log entry; raises ProvisioningStepError.
    """
    target_id = int(item.get("target_id") or 0)
    access_level_code = str(item.get("access_level_code") or "READ").strip().upper() or "READ"
    journal = lambda action, **kw: _journal(  # noqa: E731
        action, req_id=req_id, request=request, correlation_id=correlation_id, storage_root_id=target_id,
        access_level=access_level_code, **kw,
    )

    # 1. Access group of the level (database): the name comes from the naming template at the first approval
    access_group = unwrap_data(
        await call_route(
            provisioning_internal.ensure_storage_root_access_group,
            payload={
                "storage_root_id": target_id,
                "access_level_code": access_level_code,
                "group_name": str(item.get("group_ref") or "").strip(),
            },
        )
    )
    profile_id = int(access_group.get("id") or 0) or None
    group_name = str(access_group.get("group_name") or item.get("group_ref") or "").strip()
    profile_status = str(access_group.get("status") or "").strip().upper()
    external_id = str(access_group.get("group_external_id") or "").strip() or None
    adopting = profile_status == "ADOPTING"

    # 2. Group + member, on one domain controller
    try:
        queued = await queue_ad_access_grant(
            storage_root_id=target_id,
            access_profile_id=profile_id,
            identity_source_id=int(item.get("identity_source_id") or 0) or None,
            group_name=group_name,
            group_external_id=None if adopting else external_id,
            adopt_group_dn=external_id if adopting else None,
            principal_dn=principal_dn,
            principal_username=principal_username,
            access_level_code=access_level_code,
            correlation_id=f"{correlation_id}_{int(item.get('id') or 0)}_grant",
        )
    except ProvisioningStepError as exc:
        exc.details.setdefault("access_profile_id", profile_id)
        raise
    job_id = int(queued["job_id"])
    journal(
        "ad_access_grant_queued",
        result="in_progress",
        job_id=job_id,
        group_name=group_name,
        target_ou_dn=queued.get("target_ou_dn"),
        adopt_group_dn=external_id if adopting else None,
    )
    job = await wait_provisioning_job(job_id, timeout_sec=GRANT_TIMEOUT_SEC)
    if job is None:
        raise ProvisioningStepError(
            "AD_JOB_STILL_RUNNING",
            "Active Directory n'a pas encore répondu.",
            hint="The job keeps running; approve again in a few minutes (nothing is done twice).",
            job_id=job_id,
            access_profile_id=profile_id,
        )
    if str(job.get("status") or "").upper() != "SUCCEEDED":
        failure = _job_failure(job, job_id=job_id, step="ad_access_grant")
        failure.details.setdefault("access_profile_id", profile_id)
        failure.details.setdefault("group_name", group_name)
        raise failure
    grant = dict(unwrap_data(job.get("result_json") or {}).get("details") or {})
    group_name = str(grant.get("group_name") or group_name)
    journal(
        f"ad_group_{grant.get('group_outcome') or 'reused'}",
        job_id=job_id,
        group_name=group_name,
        group_dn=grant.get("group_dn"),
        target_ou_dn=grant.get("target_ou_dn"),
        directory_server=grant.get("directory_server"),
    )
    journal(
        "ad_group_member_added" if grant.get("member_outcome") == "added" else "ad_group_member_already_present",
        job_id=job_id,
        group_name=group_name,
        principal_dn=grant.get("principal_dn"),
    )

    # 3. NTFS ACL of the group on the share (idempotent: re-applied at each approval, which also repairs it)
    acl_out = await submit_probe_run(
        {
            "kind": "acl",
            "protocol": "acl_push",
            "scope": "storage_root",
            "target": {
                "storage_root_id": target_id,
                "access_level_code": access_level_code,
                "group_name": group_name,
                "permission": access_level_code,
            },
            "auth": {},
            "options": {},
            "context": {
                "storage_root_id": target_id,
                "access_level_code": access_level_code,
                "correlation_id": f"{correlation_id}_{int(item.get('id') or 0)}_acl",
            },
        }
    )
    journal("acl_apply_queued", result="in_progress", group_name=group_name, job_id=int((acl_out or {}).get("job_id") or 0) or None)
    try:
        acl_result = await _wait_acl_apply_result(acl_out, timeout_sec=ACL_TIMEOUT_SEC)
    except RuntimeError as exc:
        raise ProvisioningStepError(
            "ACL_APPLY_FAILED",
            str(exc),
            hint="The requester is in the AD group; approve again to re-apply the NTFS permissions.",
            group_name=group_name,
            access_profile_id=profile_id,
        ) from exc
    journal("acl_applied", group_name=group_name, permission=access_level_code)
    # 4. The entry reaches what the folder already contains, in the background: hours on a big tree.
    # The access is decided here; a failure shows in the Permissions tab, with its repair.
    try:
        propagation = await submit_acl_propagation(target_id, access_level_code, group_name)
        journal("acl_propagation_queued", result="in_progress", group_name=group_name, job_id=int((propagation or {}).get("job_id") or 0) or None)
    except Exception as exc:
        journal("acl_propagation_failed", result="failure", severity="warning", group_name=group_name, message=str(exc)[:300])

    return {
        "group": grant,
        "acl": {"planned": acl_out, "result": acl_result},
        "group_ref": group_name,
        "access_profile_id": profile_id,
        "identity_source_id": queued.get("identity_source_id"),
        "grant_job_id": job_id,
    }


async def _record_item_execution(
    *,
    access_request_id: int,
    access_request_item_id: int | None,
    status: str,
    requested_payload_json: dict[str, Any],
    result_json: dict[str, Any] | None,
    error_message: str | None,
) -> None:
    await call_route(
        access_requests_routes.create_access_request_item_execution_internal,
        payload={
            "access_request_id": int(access_request_id),
            "access_request_item_id": int(access_request_item_id) if access_request_item_id else None,
            "status": str(status or "DONE").upper(),
            "requested_payload_json": dict(requested_payload_json or {}),
            "result_json": dict(result_json) if isinstance(result_json, dict) else None,
            "error_message": str(error_message or "").strip() or None,
        },
    )


async def _wait_acl_apply_result(acl_out: dict[str, Any], *, timeout_sec: int = 30) -> dict[str, Any]:
    job_id = int((acl_out or {}).get("job_id") or 0)
    if job_id <= 0:
        raise RuntimeError("ACL_APPLY_JOB_MISSING")

    attempts = max(1, int(timeout_sec / 2))
    last_seen: dict[str, Any] = dict(acl_out or {})
    for _ in range(attempts):
        job = await fetch_probe_job(job_id)
        last_seen = dict(job or {})
        status_value = str(last_seen.get("status") or "").strip().lower()
        if status_value == "succeeded":
            return last_seen
        if status_value in {"failed", "timed_out", "cancelled"}:
            error = dict(last_seen.get("error") or {}) if isinstance(last_seen.get("error"), dict) else {}
            message = str(error.get("message") or error.get("code") or f"ACL apply job {status_value}").strip()
            raise RuntimeError(message or f"ACL apply job {status_value}")
        await asyncio.sleep(2)

    raise RuntimeError(f"ACL apply job did not complete within {timeout_sec} seconds")


async def _revoke_request_memberships(
    *,
    req_id: int,
    request: Request,
    correlation_id: str,
) -> str | None:
    """Remove the requester from every governed AD group of an access request (the groups are kept, even empty).

    Waits for each removal, records one item execution and log entries per item, and returns
    None on success, or the failure message (items are all attempted, failures are joined).
    """
    plan = await call_route(
        access_requests_routes.get_access_request_provisioning_plan_internal,
        access_request_id=int(req_id),
        request=request,
    )
    if not isinstance(plan, dict):
        return "Invalid provisioning plan payload"

    principal = dict(plan.get("principal") or {})
    principal_dn = str(principal.get("dn") or "").strip() or None
    principal_username = str(principal.get("username") or "").strip() or None
    items = [x for x in list(plan.get("items") or []) if isinstance(x, dict)]
    if not principal_dn and not principal_username:
        return "requested_principal_json missing dn/username"
    if not items:
        return "No access-request items found"

    failures: list[str] = []
    for item in items:
        item_id = int(item.get("id") or 0) or None
        target_type = str(item.get("target_type") or "").strip().lower()
        target_id = int(item.get("target_id") or 0)
        permission = str(item.get("permission") or "").strip().lower()
        access_level_code = str(item.get("access_level_code") or "READ").strip().upper() or "READ"
        group_ref = str(item.get("group_ref") or "").strip()
        source_id = int(item.get("identity_source_id") or 0) or None
        base_payload = {
            "storage_root_id": int(target_id),
            "access_level_code": access_level_code,
            "operation": "revoke",
        }

        error_message: str | None = None
        requested_payload: dict[str, Any] = dict(base_payload)
        if target_type != "storage_root" or target_id <= 0:
            error_message = "Unsupported target_type for AD membership revoke"
            requested_payload = {
                "target_type": target_type,
                "target_id": target_id,
                "permission": permission,
                "operation": "revoke",
            }
        elif item.get("error"):
            detail = dict(item.get("error_detail") or {}) if isinstance(item.get("error_detail"), dict) else {}
            error_message = str(detail.get("message") or item.get("error"))
            requested_payload = {**base_payload, "permission": permission, "resolution_error": detail}
        elif not group_ref:
            error_message = "Missing AD group reference"
            requested_payload = {**base_payload, "group_ref": None, "identity_source_id": source_id}

        if error_message:
            await _record_item_execution(
                access_request_id=int(req_id),
                access_request_item_id=item_id,
                status="FAILED",
                requested_payload_json=requested_payload,
                result_json=None,
                error_message=error_message,
            )
            failures.append(f"item#{item_id or 0}: {error_message}")
            continue

        requested_payload = {
            **base_payload,
            "group_ref": group_ref,
            "principal_dn": principal_dn,
            "principal_username": principal_username,
        }
        journal = lambda action, **kw: _journal(  # noqa: E731
            action, req_id=req_id, request=request, correlation_id=correlation_id, storage_root_id=target_id,
            access_level=access_level_code, group_name=group_ref, **kw,
        )
        # Another active request still grants this level: the person stays in the group
        still_granted_by = await call_route(
            access_requests_routes.other_active_request_for_level,
            access_request_id=int(req_id),
            storage_root_id=int(target_id),
            access_level_code=access_level_code,
        )
        if still_granted_by:
            journal("ad_group_member_kept", still_granted_by=still_granted_by)
            await _record_item_execution(
                access_request_id=int(req_id),
                access_request_item_id=item_id,
                status="DONE",
                requested_payload_json=requested_payload,
                result_json={"kept": True, "still_granted_by": still_granted_by},
                error_message=None,
            )
            continue
        try:
            removed = unwrap_data(
                await remove_ad_group_member(
                    RemoveAdGroupMemberIn(
                        identity_source_id=source_id,
                        group_ref=group_ref,
                        principal_dn=principal_dn,
                        principal_username=principal_username,
                    ),
                    request=_request_with_id(request, f"{correlation_id}_{int(item_id or 0)}_revoke"),
                )
            )
            job_id = int((removed or {}).get("job_id") or 0)
            journal("ad_group_member_removal_queued", result="in_progress", job_id=job_id)
            job = await wait_provisioning_job(job_id, timeout_sec=REVOKE_TIMEOUT_SEC)
            if job is None:
                raise ProvisioningStepError(
                    "AD_JOB_STILL_RUNNING",
                    "Active Directory n'a pas encore répondu : relancez la révocation dans quelques minutes.",
                    job_id=job_id,
                )
            if str(job.get("status") or "").upper() != "SUCCEEDED":
                raise _job_failure(job, job_id=job_id, step="ad_group_member_removal")
            details = dict(unwrap_data(job.get("result_json") or {}).get("details") or {})
            await call_route(
                access_requests_routes.forget_direct_membership,
                identity_source_id=source_id,
                group_ref=group_ref,
                principal_dn=principal_dn,
                principal_username=principal_username,
            )
            journal(
                "ad_group_member_removed" if details.get("reason") != "already_absent" else "ad_group_member_already_absent",
                job_id=job_id,
                principal_dn=details.get("principal_dn"),
                group_kept=True,
            )
            await _record_item_execution(
                access_request_id=int(req_id),
                access_request_item_id=item_id,
                status="DONE",
                requested_payload_json=requested_payload,
                result_json={"job_id": job_id, **details},
                error_message=None,
            )
        except Exception as exc:
            journal(
                "access_request_step_failed",
                result="failure",
                severity="warning",
                code=getattr(exc, "code", "REVOKE_FAILED"),
                message=str(getattr(exc, "message", exc))[:500],
            )
            await _record_item_execution(
                access_request_id=int(req_id),
                access_request_item_id=item_id,
                status="FAILED",
                requested_payload_json=requested_payload,
                result_json=None,
                error_message=str(exc),
            )
            failures.append(f"item#{item_id or 0}: {str(exc)[:250]}")

    return "; ".join(failures) if failures else None


async def _bulk_revoke(
    *,
    payload: dict[str, Any],
    requested_ids: list[int],
    request: Request,
) -> dict[str, Any]:
    """Revoke: remove AD memberships, then persist the revocation (internal route)."""
    failed_reasons: dict[int, str] = {}
    failed_details: dict[int, dict[str, Any]] = {}
    revoked_ids: list[int] = []

    revoke_correlations: dict[int, str] = {}
    for req_id in requested_ids:
        revoke_correlation = f"rev_{int(req_id)}_{uuid.uuid4().hex[:10]}"
        revoke_correlations[int(req_id)] = revoke_correlation
        _journal("access_request_revocation_started", req_id=int(req_id), request=request, correlation_id=revoke_correlation, result="in_progress")
        try:
            failure = await _revoke_request_memberships(
                req_id=int(req_id),
                request=request,
                correlation_id=revoke_correlation,
            )
        except Exception as exc:
            failed_reasons[int(req_id)] = str(exc)
            failed_details[int(req_id)] = {
                "item_id": None,
                "code": "REVOKE_RUNTIME_ERROR",
                "message": str(exc),
                "hint": "Check core-service logs for revoke execution details.",
            }
            continue
        if failure:
            failed_reasons[int(req_id)] = failure
            failed_details[int(req_id)] = {
                "item_id": None,
                "code": "AD_GROUP_MEMBERSHIP_REVOKE_FAILED",
                "message": failure,
                "hint": "Verify AD group membership and storage-root binding configuration.",
            }
            continue
        revoked_ids.append(int(req_id))

    persisted_data: dict[str, Any] = {}
    if revoked_ids:
        decision_comment = str(payload.get("decision_comment") or "").strip()
        result = await call_route(
            access_requests_routes.bulk_decision,
            payload={
                "ids": revoked_ids,
                "decision": "revoke",
                **({"decision_comment": decision_comment} if decision_comment else {}),
            },
            request=request,
        )
        persisted_data = unwrap_data(result) if isinstance(result, dict) else {}

    # JSON object keys come back as strings
    persisted_reasons = {str(k): v for k, v in dict(persisted_data.get("failed_reasons") or {}).items()}
    persisted_details = {str(k): v for k, v in dict(persisted_data.get("failed_details") or {}).items()}
    for raw_id in list(persisted_data.get("failed_ids") or []):
        req_id = int(raw_id)
        failed_reasons[req_id] = str(persisted_reasons.get(str(req_id)) or "Revoke failed")
        failed_details[req_id] = dict(persisted_details.get(str(req_id)) or {"message": failed_reasons[req_id]})

    failed_ids = [int(x) for x in requested_ids if int(x) in failed_reasons]
    updated_ids = [int(x) for x in revoked_ids if int(x) not in failed_reasons]
    for req_id in requested_ids:
        ok = int(req_id) in updated_ids
        _journal(
            "access_request_revoked" if ok else "access_request_revocation_failed",
            req_id=int(req_id),
            request=request,
            correlation_id=revoke_correlations[int(req_id)],
            result="success" if ok else "failure",
            severity="info" if ok else "warning",
            message=None if ok else str(failed_reasons.get(int(req_id)) or "")[:500],
        )
    return ui_data({
        "ok": len(failed_ids) == 0,
        "decision": "revoke",
        "requested_ids": requested_ids,
        "updated_ids": updated_ids,
        "failed_ids": failed_ids,
        "failed_reasons": {int(k): v for k, v in failed_reasons.items() if int(k) in failed_ids},
        "failed_details": {
            int(k): _normalize_failed_detail(v) for k, v in failed_details.items() if int(k) in failed_ids
        },
        "updated_count": int(len(updated_ids)),
        "executions_started": int(len(updated_ids)),
    })


_approvals_in_progress = access_requests_routes.approvals_in_progress
_ALREADY_DECIDED = {
    "code": "REQUEST_ALREADY_DECIDED",
    "message": "Cette demande a déjà été traitée.",
    "hint": "Actualisez la liste : rien n'a été modifié.",
}


async def _split_already_decided(requested_ids: list[int], request: Request) -> tuple[list[int], list[int]]:
    undecided: list[int] = []
    decided: list[int] = []
    for req_id in requested_ids:
        details = unwrap_data(
            await call_route(access_requests_routes.get_access_request_details, access_request_id=int(req_id), request=request)
        )
        status_value = str((details or {}).get("status") or "pending").strip().lower()
        (undecided if any(key in status_value for key in ("pending", "waiting", "review")) else decided).append(int(req_id))
    return undecided, decided


def _with_already_decided(
    result: dict[str, Any],
    decision: str,
    requested_ids: list[int],
    undecided: list[int],
    already_decided: list[int],
) -> dict[str, Any]:
    merged = dict(result or {})
    merged.setdefault("ok", True)
    merged["decision"] = decision
    merged["requested_ids"] = requested_ids
    merged.setdefault("updated_ids", [])
    merged.setdefault("updated_count", 0)
    merged.setdefault("executions_started", 0)
    merged["failed_ids"] = [*list(merged.get("failed_ids") or []), *already_decided]
    merged["failed_reasons"] = {**dict(merged.get("failed_reasons") or {}), **{i: _ALREADY_DECIDED["message"] for i in already_decided}}
    merged["failed_details"] = {**dict(merged.get("failed_details") or {}), **{i: dict(_ALREADY_DECIDED) for i in already_decided}}
    return merged


@router.post("/bulk")
async def bulk_decision(request: Request) -> dict[str, Any]:
    payload = await request.json()
    decision = str((payload or {}).get("decision") or "").strip().lower()
    requested_ids = _normalize_ids((payload or {}).get("ids"))

    if not str(request.headers.get("x-identity-id") or "").strip():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "REVIEWER_CONTEXT_REQUIRED",
                "message": "Reviewer identity is required for access-request decisions.",
            },
        )

    if decision == "revoke":
        return await _bulk_revoke(
            payload=payload or {},
            requested_ids=requested_ids,
            request=request,
        )

    # Approving or rejecting is for pending requests only: the access of a decided one is already in place, or refused
    undecided, already_decided = await _split_already_decided(requested_ids, request)

    if decision != "approve":
        result = {}
        if undecided:
            result = unwrap_data(
                await call_route(
                    access_requests_routes.bulk_decision,
                    payload={**payload, "ids": undecided},
                    request=request,
                )
            )
        return ui_data(_with_already_decided(result, decision, requested_ids, undecided, already_decided))

    await call_route(access_requests_routes.ensure_requests_approvable, ids=undecided, request=request)

    # A second reviewer clicking while the approval runs (the status changes at its end)
    in_progress = [req_id for req_id in undecided if req_id in _approvals_in_progress]
    claimed = [req_id for req_id in undecided if req_id not in _approvals_in_progress]
    already_decided.extend(in_progress)
    _approvals_in_progress.update(claimed)
    try:
        return await _bulk_approve(payload=payload, requested_ids=claimed, already_decided=already_decided, request=request)
    finally:
        _approvals_in_progress.difference_update(claimed)


async def _bulk_approve(
    *,
    payload: dict[str, Any],
    requested_ids: list[int],
    already_decided: list[int],
    request: Request,
) -> dict[str, Any]:
    failed_ids: list[int] = list(already_decided)
    failed_reasons: dict[int, str] = {req_id: _ALREADY_DECIDED["message"] for req_id in already_decided}
    failed_details: dict[int, dict[str, Any]] = {req_id: dict(_ALREADY_DECIDED) for req_id in already_decided}
    approved_ids: list[int] = []
    executions_started = 0

    approval_correlations: dict[int, str] = {}
    for req_id in requested_ids:
        # One correlation per approval attempt: a new attempt runs new jobs (retry after a failure)
        approval_correlation = f"apr_{int(req_id)}_{uuid.uuid4().hex[:10]}"
        _journal("access_request_approval_started", req_id=int(req_id), request=request, correlation_id=approval_correlation, result="in_progress")
        try:
            plan = await call_route(
                access_requests_routes.get_access_request_provisioning_plan_internal,
                access_request_id=int(req_id),
                request=request,
            )
            if not isinstance(plan, dict):
                failed_ids.append(int(req_id))
                failed_reasons[int(req_id)] = "Invalid provisioning plan payload"
                failed_details[int(req_id)] = {
                    "item_id": None,
                    "code": "PROVISIONING_PLAN_INVALID",
                    "message": "Invalid provisioning plan payload",
                    "hint": "Retry and verify the provisioning-plan contract.",
                    "storage_root_id": None,
                    "requested_permission": None,
                    "candidates_count": 0,
                }
                continue

            principal = dict(plan.get("principal") or {})
            principal_dn = str(principal.get("dn") or "").strip() or None
            principal_username = str(principal.get("username") or "").strip() or None
            items = [x for x in list(plan.get("items") or []) if isinstance(x, dict)]

            if not principal_dn and not principal_username:
                for item in items:
                    item_id = int(item.get("id") or 0) or None
                    item_correlation = f"ar_{int(req_id)}_{int(item_id or 0)}"
                    await _record_item_execution(
                        access_request_id=int(req_id),
                        access_request_item_id=item_id,
                        status="FAILED",
                        requested_payload_json={
                            "correlation_id": f"{item_correlation}_principal",
                            "target_type": item.get("target_type"),
                            "target_id": item.get("target_id"),
                            "permission": item.get("permission"),
                        },
                        result_json=None,
                        error_message="requested_principal_json missing dn/username",
                    )
                failed_ids.append(int(req_id))
                failed_reasons[int(req_id)] = "requested_principal_json missing dn/username"
                failed_details[int(req_id)] = {
                    "item_id": None,
                    "code": "REQUESTED_PRINCIPAL_MISSING",
                    "message": "requested_principal_json missing dn/username",
                    "hint": "Set requested principal DN or username before approval.",
                    "storage_root_id": None,
                    "requested_permission": None,
                    "candidates_count": 0,
                }
                continue

            request_failures: list[str] = []
            request_failure_details: list[dict[str, Any]] = []
            for item in items:
                item_id = int(item.get("id") or 0) or None
                item_error = str(item.get("error") or "").strip() or None
                item_error_detail = dict(item.get("error_detail") or {}) if isinstance(item.get("error_detail"), dict) else {}
                target_id = int(item.get("target_id") or 0)
                access_level_code = str(item.get("access_level_code") or "READ").strip().upper() or "READ"
                group_ref = str(item.get("group_ref") or "").strip()
                source_id = int(item.get("identity_source_id") or 0) or None
                item_correlation = f"ar_{int(req_id)}_{int(item_id or 0)}"

                if item_error:
                    detail_payload = {
                        "item_id": int(item_id or 0) or None,
                        "code": str(item_error_detail.get("code") or "ACCESS_REQUEST_ITEM_PLAN_ERROR"),
                        "message": str(item_error_detail.get("message") or item_error),
                        "hint": str(item_error_detail.get("hint") or "Resolve storage-root binding configuration and retry approval."),
                        "storage_root_id": (
                            int(item_error_detail.get("storage_root_id") or target_id or 0) or None
                        ),
                        "requested_permission": (
                            str(item_error_detail.get("requested_permission") or access_level_code).upper() or None
                        ),
                        "candidates_count": int(item_error_detail.get("candidates_count") or 0),
                        "repair_attempted": bool(item_error_detail.get("repair_attempted") or False),
                        "repair_result": str(item_error_detail.get("repair_result") or "").strip() or None,
                    }
                    await _record_item_execution(
                        access_request_id=int(req_id),
                        access_request_item_id=item_id,
                        status="FAILED",
                        requested_payload_json={
                            "correlation_id": f"{item_correlation}_plan",
                            "target_type": item.get("target_type"),
                            "target_id": item.get("target_id"),
                            "permission": item.get("permission"),
                        },
                        result_json=None,
                        error_message=item_error,
                    )
                    request_failures.append(f"item#{item_id or 0}: {item_error}")
                    request_failure_details.append(detail_payload)
                    continue

                requested_payload = {
                    "correlation_id": f"{approval_correlation}_{int(item_id or 0)}",
                    "storage_root_id": int(target_id),
                    "access_level_code": access_level_code,
                    "group_ref": group_ref,
                    "identity_source_id": source_id,
                    "principal_dn": principal_dn,
                    "principal_username": principal_username,
                }
                try:
                    result = await _grant_item(
                        req_id=int(req_id),
                        item=item,
                        principal_dn=principal_dn,
                        principal_username=principal_username,
                        request=request,
                        correlation_id=approval_correlation,
                    )
                    await _record_item_execution(
                        access_request_id=int(req_id),
                        access_request_item_id=item_id,
                        status="DONE",
                        requested_payload_json={**requested_payload, "group_ref": result.get("group_ref")},
                        result_json=result,
                        error_message=None,
                    )
                except Exception as exc:
                    step_error = exc if isinstance(exc, ProvisioningStepError) else ProvisioningStepError(
                        "APPROVAL_EXECUTION_FAILED", str(exc), hint="Check provisioning traces and retry approval."
                    )
                    detail_payload = {
                        "item_id": int(item_id or 0) or None,
                        "code": step_error.code,
                        "message": step_error.message,
                        "hint": step_error.hint or "Check provisioning traces and retry approval.",
                        "storage_root_id": int(target_id or 0) or None,
                        "requested_permission": access_level_code,
                        "candidates_count": 0,
                        **step_error.details,
                    }
                    _journal(
                        "access_request_step_failed",
                        req_id=int(req_id),
                        request=request,
                        correlation_id=approval_correlation,
                        storage_root_id=int(target_id or 0) or None,
                        result="failure",
                        severity="warning",
                        code=step_error.code,
                        message=step_error.message,
                        hint=step_error.hint,
                        **{k: v for k, v in step_error.details.items() if isinstance(v, (str, int))},
                    )
                    await _record_item_execution(
                        access_request_id=int(req_id),
                        access_request_item_id=item_id,
                        status="FAILED",
                        requested_payload_json={**requested_payload, "error_code": step_error.code},
                        result_json=None,
                        error_message=step_error.message,
                    )
                    request_failures.append(f"item#{item_id or 0}: {step_error.message[:250]}")
                    request_failure_details.append(detail_payload)

            if request_failures:
                _journal(
                    "access_request_approval_failed",
                    req_id=int(req_id),
                    request=request,
                    correlation_id=approval_correlation,
                    result="failure",
                    severity="warning",
                    message="; ".join(request_failures)[:500],
                )
                failed_ids.append(int(req_id))
                normalized_messages = [
                    str((d or {}).get("message") or "").strip()
                    for d in request_failure_details
                    if isinstance(d, dict)
                ]
                normalized_messages = [m for m in normalized_messages if m]
                failed_reasons[int(req_id)] = (
                    "; ".join(normalized_messages)
                    if normalized_messages
                    else "; ".join(request_failures)
                )
                failed_details[int(req_id)] = (
                    dict(request_failure_details[0])
                    if request_failure_details
                    else {
                        "item_id": None,
                        "code": "APPROVAL_FAILED",
                        "message": failed_reasons[int(req_id)],
                        "hint": "Resolve item-level errors and retry approval.",
                        "storage_root_id": None,
                        "requested_permission": None,
                        "candidates_count": 0,
                    }
                )
                continue

            approved_ids.append(int(req_id))
            approval_correlations[int(req_id)] = approval_correlation
            executions_started += 1
        except HTTPException as exc:
            # Not allowed to decide: a refusal, not a failed approval to retry
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                raise
            _journal(
                "access_request_approval_failed",
                req_id=int(req_id),
                request=request,
                correlation_id=approval_correlation,
                result="failure",
                severity="warning",
                message=str(exc.detail)[:500],
            )
            failed_ids.append(int(req_id))
            failed_reasons[int(req_id)] = str(exc.detail)
            failed_details[int(req_id)] = {"item_id": None, "code": "APPROVAL_PLAN_RUNTIME_ERROR", "message": str(exc.detail), "hint": "Retry and inspect core-service logs.", "storage_root_id": None, "requested_permission": None, "candidates_count": 0}
        except Exception as exc:
            _journal(
                "access_request_approval_failed",
                req_id=int(req_id),
                request=request,
                correlation_id=approval_correlation,
                result="failure",
                severity="warning",
                message=str(exc)[:500],
            )
            failed_ids.append(int(req_id))
            failed_reasons[int(req_id)] = str(exc)
            failed_details[int(req_id)] = {
                "item_id": None,
                "code": "APPROVAL_PLAN_RUNTIME_ERROR",
                "message": str(exc),
                "hint": "Retry and inspect core-service logs.",
                "storage_root_id": None,
                "requested_permission": None,
                "candidates_count": 0,
            }

    if approved_ids:
        decision_comment = str((payload or {}).get("decision_comment") or "").strip()
        await call_route(
            access_requests_routes.bulk_decision,
            payload={
                "ids": approved_ids,
                "decision": "approve",
                **({"decision_comment": decision_comment} if decision_comment else {}),
            },
            request=request,
        )
        for req_id in approved_ids:
            _journal("access_request_applied", req_id=int(req_id), request=request, correlation_id=approval_correlations[int(req_id)])

    normalized_failed_ids = [int(x) for x in failed_ids if int(x) > 0]
    normalized_failed_details = {
        int(req_id): _normalize_failed_detail(failed_details.get(int(req_id)))
        for req_id in normalized_failed_ids
    }
    normalized_failed_reasons: dict[int, str] = {}
    for req_id in normalized_failed_ids:
        reason = str(failed_reasons.get(int(req_id)) or "").strip()
        if not reason:
            reason = str((normalized_failed_details.get(int(req_id)) or {}).get("message") or "").strip()
        normalized_failed_reasons[int(req_id)] = reason or "Approval failed"

    result_payload = {
        "ok": len(normalized_failed_ids) == 0,
        "decision": "approve",
        "requested_ids": requested_ids,
        "updated_ids": approved_ids,
        "failed_ids": normalized_failed_ids,
        "failed_reasons": normalized_failed_reasons,
        "failed_details": normalized_failed_details,
        "updated_count": int(len(approved_ids)),
        "executions_started": int(executions_started),
    }
    return ui_data(result_payload)
