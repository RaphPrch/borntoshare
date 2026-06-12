from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.core.dal_client import dal_get, dal_post
from app.schemas.api_envelopes import data_envelope
from app.schemas.provisioning import EnsureAdGroupContextIn, EnsureAdGroupIn, EnsureAdGroupMemberIn
from app.api.provisioning import ensure_ad_group_member, ensure_ad_group_via_name
from app.services.probe_service import fetch_probe_job, submit_probe_run


router = APIRouter(prefix="/access-requests", tags=["access-requests"])


def _unwrap_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


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


def _actor_forward_headers(request: Request) -> dict[str, str]:
    headers = getattr(request, "headers", {}) or {}
    out: dict[str, str] = {}
    for key in ("x-identity-id", "x-roles", "x-actor-display"):
        value = str(headers.get(key) or "").strip()
        if value:
            out[key] = value
    return out


async def _record_item_execution(
    *,
    request_id: str | None,
    access_request_id: int,
    access_request_item_id: int | None,
    status: str,
    requested_payload_json: dict[str, Any],
    result_json: dict[str, Any] | None,
    error_message: str | None,
) -> None:
    await dal_post(
        "/api/internal/access-requests/item-executions",
        {
            "access_request_id": int(access_request_id),
            "access_request_item_id": int(access_request_item_id) if access_request_item_id else None,
            "status": str(status or "DONE").upper(),
            "requested_payload_json": dict(requested_payload_json or {}),
            "result_json": dict(result_json) if isinstance(result_json, dict) else None,
            "error_message": str(error_message or "").strip() or None,
        },
        timeout=8,
        request_id=request_id,
        retries=1,
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


@router.post("/bulk")
async def bulk_decision(request: Request) -> dict[str, Any]:
    payload = await request.json()
    request_headers = getattr(request, "headers", {})
    request_id = request_headers.get("x-request-id") or None
    actor_headers = _actor_forward_headers(request)
    decision = str((payload or {}).get("decision") or "").strip().lower()
    requested_ids = _normalize_ids((payload or {}).get("ids"))

    if "x-identity-id" not in actor_headers:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "REVIEWER_CONTEXT_REQUIRED",
                "message": "Reviewer identity is required for access-request decisions.",
            },
        )

    if decision != "approve":
        result = await dal_post(
            "/api/access-requests/bulk",
            payload,
            timeout=30,
            request_id=request_id,
            retries=2,
            extra_headers=actor_headers,
        )
        return data_envelope(_unwrap_data(result))

    failed_ids: list[int] = []
    failed_reasons: dict[int, str] = {}
    failed_details: dict[int, dict[str, Any]] = {}
    approved_ids: list[int] = []
    executions_started = 0

    for req_id in requested_ids:
        try:
            plan = await dal_get(
                f"/api/internal/access-requests/{int(req_id)}/provisioning-plan",
                timeout=8,
                request_id=request_id,
                retries=1,
                extra_headers=actor_headers,
            )
            if not isinstance(plan, dict):
                failed_ids.append(int(req_id))
                failed_reasons[int(req_id)] = "Invalid provisioning plan payload"
                failed_details[int(req_id)] = {
                    "item_id": None,
                    "code": "PROVISIONING_PLAN_INVALID",
                    "message": "Invalid provisioning plan payload",
                    "hint": "Retry and verify provisioning-plan contract between DAL and Governance.",
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
                        request_id=request_id,
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
                profile_status = str(item.get("profile_status") or "").strip().upper()
                group_external_id = str(item.get("group_external_id") or "").strip() or None
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
                        request_id=request_id,
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

                try:
                    ensure_request = _request_with_id(request, f"{item_correlation}_group")
                    ensured_group: dict[str, Any] | None = None
                    profile_already_provisioned = profile_status in {"SUCCEEDED"} and bool(group_external_id)
                    if not profile_already_provisioned:
                        ensure_out = await ensure_ad_group_via_name(
                            EnsureAdGroupIn(
                                group_name=group_ref,
                                identity_source_id=source_id,
                                context=EnsureAdGroupContextIn(
                                    storage_root_id=int(target_id),
                                ),
                            ),
                            request=ensure_request,
                        )
                        ensured_group = _unwrap_data(ensure_out) if isinstance(ensure_out, dict) else None

                    member_request = _request_with_id(request, f"{item_correlation}_member")
                    member_out = await ensure_ad_group_member(
                        EnsureAdGroupMemberIn(
                            identity_source_id=source_id,
                            group_ref=group_ref,
                            principal_dn=principal_dn,
                            principal_username=principal_username,
                        ),
                        request=member_request,
                    )
                    ensured_member = _unwrap_data(member_out) if isinstance(member_out, dict) else None

                    acl_out = await submit_probe_run(
                        {
                            "kind": "acl",
                            "protocol": "acl_push",
                            "scope": "storage_root",
                                "target": {
                                    "storage_root_id": int(target_id),
                                    "access_level_code": access_level_code,
                                    "group_name": group_ref,
                                    "permission": access_level_code,
                                },
                            "auth": {},
                            "options": {},
                            "context": {
                                "storage_root_id": int(target_id),
                                "access_level_code": access_level_code,
                                "correlation_id": f"{item_correlation}_acl",
                            },
                        }
                    )
                    acl_result = await _wait_acl_apply_result(acl_out)

                    result = {
                        "group": ensured_group,
                        "membership": ensured_member,
                        "acl": {
                            "planned": acl_out,
                            "result": acl_result,
                        },
                        "group_ref": group_ref,
                        "profile_status": profile_status,
                        "group_external_id": group_external_id,
                        "group_create_skipped": profile_already_provisioned,
                        "identity_source_id": source_id,
                    }
                    await _record_item_execution(
                        request_id=request_id,
                        access_request_id=int(req_id),
                        access_request_item_id=item_id,
                        status="DONE",
                        requested_payload_json={
                            "correlation_id": f"{item_correlation}_done",
                            "storage_root_id": int(target_id),
                            "access_level_code": access_level_code,
                            "group_ref": group_ref,
                            "identity_source_id": source_id,
                            "principal_dn": principal_dn,
                            "principal_username": principal_username,
                        },
                        result_json=result,
                        error_message=None,
                    )
                except Exception as exc:
                    detail_payload = {
                        "item_id": int(item_id or 0) or None,
                        "code": "APPROVAL_EXECUTION_FAILED",
                        "message": str(exc),
                        "hint": "Check provisioning traces and retry approval.",
                        "storage_root_id": int(target_id or 0) or None,
                        "requested_permission": access_level_code,
                        "candidates_count": 0,
                    }
                    await _record_item_execution(
                        request_id=request_id,
                        access_request_id=int(req_id),
                        access_request_item_id=item_id,
                        status="FAILED",
                        requested_payload_json={
                            "correlation_id": f"{item_correlation}_failed",
                            "storage_root_id": int(target_id),
                            "access_level_code": access_level_code,
                            "group_ref": group_ref,
                            "identity_source_id": source_id,
                            "principal_dn": principal_dn,
                            "principal_username": principal_username,
                        },
                        result_json=None,
                        error_message=str(exc),
                    )
                    request_failures.append(f"item#{item_id or 0}: {str(exc)[:250]}")
                    request_failure_details.append(detail_payload)

            if request_failures:
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
            executions_started += 1
        except Exception as exc:
            failed_ids.append(int(req_id))
            failed_reasons[int(req_id)] = str(exc)
            failed_details[int(req_id)] = {
                "item_id": None,
                "code": "APPROVAL_PLAN_RUNTIME_ERROR",
                "message": str(exc),
                "hint": "Retry and inspect Governance/DAL logs.",
                "storage_root_id": None,
                "requested_permission": None,
                "candidates_count": 0,
            }

    if approved_ids:
        decision_comment = str((payload or {}).get("decision_comment") or "").strip()
        await dal_post(
            "/api/access-requests/bulk",
            {
                "ids": approved_ids,
                "decision": "approve",
                **({"decision_comment": decision_comment} if decision_comment else {}),
            },
            timeout=30,
            request_id=request_id,
            retries=2,
            extra_headers=actor_headers,
        )

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
    return data_envelope(result_payload)
