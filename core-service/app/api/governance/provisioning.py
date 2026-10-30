from __future__ import annotations

import asyncio
import re
import time
import uuid
from typing import Any

from fastapi import Depends, APIRouter, HTTPException, Query, Request, Response, status

from app.api import provisioning_internal
from app.core.direct_call import call_route
from app.api._helpers import ui_data, ui_list
from app.jobs.b2s_job_contracts.actors import publish_job, run_provisioning_job
from app.jobs.b2s_job_contracts.contracts import queue_job_types_csv
from app.schemas.provisioning import EnsureAdGroupIn, EnsureAdGroupMemberIn, RemoveAdGroupMemberIn
from app.services.identity_capsule_payloads import (
    build_identity_source_capsule_context,
    infer_identity_source_id_from_group_ref,
)
from app.services.audit_logger import log_event
from app.services.authorization import actor_from_request, admin_only, require_admin
from app.services.provisioning_context import build_provisioning_context
from app.services.provisioning_jobs import create_and_publish_job


router = APIRouter(tags=["provisioning"])


def _normalize_job_status(raw: str | None) -> str:
    value = str(raw or "").strip().upper()
    aliases = {
        "PENDING": "QUEUED",
        "QUEUE": "QUEUED",
        "SUCCESS": "SUCCEEDED",
        "DONE": "SUCCEEDED",
        "OK": "SUCCEEDED",
        "ACTIVE": "SUCCEEDED",
        "CANCELED": "CANCELLED",
    }
    return aliases.get(value, value)


def _normalize_access_level(value: str) -> str:
    level = str(value or "").strip().upper()
    if level not in {"READ", "WRITE"}:
        raise HTTPException(status_code=422, detail="access_level must be READ or WRITE")
    return level


def _request_actor_context(request: Request | None) -> tuple[str | None, str | None]:
    if request is None:
        return None, None
    actor_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")
    return actor_ip, user_agent


_DN_RDN_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9-]*)\s*=\s*(.+?)\s*$")


def _collapse_repeated_dc_suffix(segments: list[str]) -> list[str]:
    dc_start = next((idx for idx, segment in enumerate(segments) if segment.upper().startswith("DC=")), -1)
    if dc_start < 0:
        return segments

    prefix = list(segments[:dc_start])
    dc_suffix = list(segments[dc_start:])
    while len(dc_suffix) >= 2 and (len(dc_suffix) % 2 == 0):
        half = len(dc_suffix) // 2
        if dc_suffix[:half] != dc_suffix[half:]:
            break
        dc_suffix = dc_suffix[:half]
    return [*prefix, *dc_suffix]


def _canonicalize_target_ou_dn(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("DN is empty")

    raw_segments = [part.strip() for part in re.split(r"(?<!\\),", raw)]
    if not raw_segments or any(not part for part in raw_segments):
        raise ValueError("DN contains empty segment(s)")

    normalized: list[str] = []
    for segment in raw_segments:
        match = _DN_RDN_RE.match(segment)
        if not match:
            raise ValueError(f"Invalid DN segment: {segment}")
        attr = str(match.group(1) or "").strip().upper()
        rdn_value = str(match.group(2) or "").strip()
        if not attr or not rdn_value:
            raise ValueError(f"Invalid DN segment: {segment}")
        normalized.append(f"{attr}={rdn_value}")

    normalized = _collapse_repeated_dc_suffix(normalized)
    if not any(part.startswith("DC=") for part in normalized):
        raise ValueError("DN must include at least one DC segment")

    return ",".join(normalized)


def _job_envelope(*, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": action,
        "payload": payload,
    }


async def _resolve_identity_source_id_for_group_operation(
    *,
    identity_source_id: int | None,
    group_ref: str,
) -> int:
    resolved_id = int(identity_source_id or 0) or None
    if resolved_id:
        return int(resolved_id)
    return int(await infer_identity_source_id_from_group_ref(group_ref))


def access_group_description(root_path: Any, access_level_code: str | None = None) -> str | None:
    """Description of an AD group created by BornToShare: the folder it opens on the file server, then the level.

    Admins read it in « Active Directory Users and Computers » to know what the group gives access to.
    """
    path = str(root_path or "").strip()
    if not path:
        return None
    level = {"READ": "lecture", "WRITE": "modification"}.get(str(access_level_code or "").strip().upper())
    return f"{path} — {'accès ' + level if level else 'accès'} (BornToShare)"[:1024]


async def ensure_ad_group_via_name(
    payload: EnsureAdGroupIn,
    request: Request = None,
    response: Response = None,
):
    correlation_id = (request.headers.get("x-request-id") if request else None) or f"adg_{uuid.uuid4().hex}"

    group_name = str(payload.group_name or "").strip()
    if not group_name:
        raise HTTPException(status_code=422, detail="group_name is required")

    root_id = int((payload.context.storage_root_id if payload.context else 0) or 0)
    target_ou_dn = str(payload.target_ou_dn or "").strip() or None
    secret_ref = str(payload.secret_ref or "").strip() or None
    domain_name = str(payload.domain_name or "").strip() or None
    identity_source_id = int(payload.identity_source_id or 0) or None
    access_group_id = int((payload.context.storage_root_access_profile_id if payload.context else 0) or 0) or None
    resolved_host = str(payload.directory_server_hint or "").strip() or None
    resolved_port: int | None = None
    resolved_protocol: str | None = None
    resolved_bind_dn: str | None = None

    description_text = str(payload.description_text or "").strip() or None
    if root_id > 0:
        ctx = await call_route(provisioning_internal.get_storage_root_provisioning_context, storage_root_id=int(root_id))
        pctx = build_provisioning_context(ctx)
        description_text = access_group_description((ctx or {}).get("root_path")) or description_text

        secret_ref = secret_ref or pctx.effective_secret_ref
        identity_source_id = identity_source_id or pctx.identity_source_id
        domain_name = domain_name or pctx.domain_name
        resolved_host = resolved_host or pctx.resolved_host
        resolved_port = resolved_port or pctx.resolved_port
        resolved_protocol = resolved_protocol or pctx.resolved_protocol
        resolved_bind_dn = resolved_bind_dn or pctx.resolved_bind_dn
        target_ou_dn = target_ou_dn or pctx.effective_group_ou_dn

    if not target_ou_dn:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "target_ou_dn is required",
                "hint": "Configure zone provisioning base_ou_dn and/or identity_sources.default_group_ou_dn",
                "storage_root_id": root_id or None,
            },
        )
    try:
        target_ou_dn = _canonicalize_target_ou_dn(target_ou_dn)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_TARGET_OU_DN",
                "message": "target_ou_dn is invalid",
                "hint": "Expected LDAP DN, e.g. OU=Groups,DC=corp,DC=local",
                "reason": str(exc),
                "target_ou_dn": str(target_ou_dn or "").strip() or None,
                "storage_root_id": root_id or None,
            },
        ) from exc
    if not secret_ref:
        raise HTTPException(status_code=422, detail="secret_ref is required (or provide context.storage_root_id)")

    if access_group_id:
        # A creation job is already in flight for this access group: do not queue another one.
        active_jobs = await call_route(
            provisioning_internal.list_provisioning_jobs,
            storage_root_access_profile_id=int(access_group_id),
            job_type="AD_GROUP_ENSURE",
            active_only=True,
            limit=1,
        )
        existing_job = active_jobs[0] if isinstance(active_jobs, list) and active_jobs else None
        if isinstance(existing_job, dict):
            existing_status = _normalize_job_status(str(existing_job.get("status") or "QUEUED"))
            if existing_status in {"QUEUED", "RUNNING", "RETRYING"}:
                if response is not None:
                    response.status_code = status.HTTP_202_ACCEPTED
                return ui_data({
                    "ok": True,
                    "job_id": int(existing_job.get("id") or 0),
                    "status": existing_status,
                    "correlation_id": existing_job.get("correlation_id"),
                    "group_name": group_name,
                    "target_ou_dn": target_ou_dn,
                })

    try:
        created = await create_and_publish_job(
            payload={
                "correlation_id": correlation_id,
                "job_type": "AD_GROUP_ENSURE",
                "action": "ensure_ad_group",
                "status": "QUEUED",
                "identity_source_id": identity_source_id,
                "storage_root_access_profile_id": access_group_id,
                "payload_json": _job_envelope(
                    action="ensure_ad_group",
                    payload={
                    "template": {"slug": "ensure_ad_group", "version": "v1"},
                    "group_name": group_name,
                    "target_ou_dn": target_ou_dn,
                    "directory_server_hint": resolved_host or payload.directory_server_hint,
                    "host": resolved_host,
                    "port": resolved_port,
                    "protocol": resolved_protocol,
                    "bind_dn": resolved_bind_dn,
                    "description_text": description_text,
                    "domain_name": domain_name,
                    "secret_ref": secret_ref,
                    "context": {
                        "storage_root_id": root_id or None,
                        "storage_root_access_profile_id": access_group_id,
                        "zone_id": int((payload.context.zone_id if payload.context else 0) or 0) or None,
                        "correlation_id": correlation_id,
                    },
                    },
                ),
            },
            actor=run_provisioning_job,
        )
        job_id = int(created.get("job_id") or 0)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error_code": str(exc), "message": "Failed to create AD group ensure job"},
        ) from exc

    actor_id = (
        (request.headers.get("x-identity-id") if request else None)
        or (request.headers.get("x-service-name") if request else None)
        or "system"
    )
    actor_ip, user_agent = _request_actor_context(request)
    log_event(
        action="ad_group_ensure_queued",
        event_category="PROVISIONING",
        event_scope="business",
        actor_type="user" if str(actor_id).isdigit() else "service",
        actor_id=actor_id,
        entity_type="ad_group",
        entity_id=None,
        zone_id=int((payload.context.zone_id if payload.context else 0) or 0) or None,
        storage_root_id=root_id or None,
        correlation_id=correlation_id,
        result="in_progress",
        severity="info",
        metadata_json={
            "before": None,
            "after": {"status": "QUEUED"},
            "details": {
                "job_id": job_id,
                "group_name": group_name,
                "target_ou_dn": target_ou_dn,
            },
        },
        actor_ip=actor_ip,
        user_agent=user_agent,
    )

    if response is not None:
        response.status_code = status.HTTP_202_ACCEPTED

    return ui_data({
        "ok": True,
        "job_id": job_id,
        "status": "QUEUED",
        "correlation_id": correlation_id,
        "group_name": group_name,
        "target_ou_dn": target_ou_dn,
    })


class ProvisioningStepError(RuntimeError):
    """A provisioning step that cannot run or failed, with what the reviewer needs to fix it."""

    def __init__(self, code: str, message: str, *, hint: str | None = None, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details


TERMINAL_JOB_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED"}


async def wait_provisioning_job(job_id: int, *, timeout_sec: float = 60, interval_sec: float = 1.0) -> dict[str, Any] | None:
    """Final state of a provisioning job, or None if it is still running after timeout_sec."""
    deadline = time.monotonic() + max(0.0, float(timeout_sec))
    while True:
        job = await call_route(provisioning_internal.get_provisioning_job_by_id, job_id=int(job_id))
        job = dict(job or {})
        if _normalize_job_status(str(job.get("status") or "")) in TERMINAL_JOB_STATUSES:
            return job
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(interval_sec)


async def queue_ad_access_grant(
    *,
    storage_root_id: int,
    access_profile_id: int | None,
    identity_source_id: int | None,
    group_name: str,
    group_external_id: str | None,
    adopt_group_dn: str | None,
    principal_dn: str | None,
    principal_username: str | None,
    access_level_code: str | None,
    correlation_id: str,
) -> dict[str, Any]:
    """Queue the capsule job that finds/creates the AD group of the level and adds the requester.

    The configuration is checked first so that nothing reaches AD when the zone is not ready.
    """
    ctx = await call_route(provisioning_internal.get_storage_root_provisioning_context, storage_root_id=int(storage_root_id))
    pctx = build_provisioning_context(ctx)
    description_text = access_group_description((ctx or {}).get("root_path") if isinstance(ctx, dict) else None, access_level_code)
    source_id = int(identity_source_id or 0) or pctx.identity_source_id
    if not source_id:
        raise ProvisioningStepError(
            "IDENTITY_SOURCE_REQUIRED",
            "The storage endpoint of this root has no Active Directory identity source.",
            hint="Link an Active Directory identity source to the storage endpoint.",
        )
    if not pctx.effective_group_ou_dn:
        raise ProvisioningStepError(
            "ZONE_GROUP_OU_MISSING",
            "No organizational unit is configured for the groups of this zone.",
            hint="Set the organizational unit in Zones › Provisioning.",
            zone_id=pctx.zone_id,
        )
    try:
        target_ou_dn = _canonicalize_target_ou_dn(pctx.effective_group_ou_dn)
    except ValueError as exc:
        raise ProvisioningStepError(
            "INVALID_TARGET_OU_DN",
            "The organizational unit of the zone is not a valid LDAP DN.",
            hint="Expected e.g. OU=Groups,DC=example,DC=org (Zones › Provisioning).",
            target_ou_dn=pctx.effective_group_ou_dn,
            reason=str(exc),
        ) from exc
    try:
        capsule_ctx = await build_identity_source_capsule_context(int(source_id), purpose="provisioning")
    except HTTPException as exc:
        if isinstance(exc.detail, dict) and exc.detail.get("error_code") == "AD_PROVISIONING_DISABLED":
            raise ProvisioningStepError(
                "AD_PROVISIONING_DISABLED",
                "Managing AD groups is disabled for this identity source.",
                hint="Enable “Manage AD groups” on the identity source.",
                identity_source_id=int(source_id),
            ) from exc
        raise ProvisioningStepError(
            "IDENTITY_SOURCE_INCOMPLETE",
            "The Active Directory identity source is not usable for provisioning.",
            hint="Check host, bind account, password and base DN of the identity source.",
            identity_source_id=int(source_id),
            reason=exc.detail,
        ) from exc

    capsule_payload = {
        **capsule_ctx,
        "timeout": 15,
        "target_ou_dn": target_ou_dn,
        "group_name": str(group_name or "").strip(),
        "group_external_id": str(group_external_id or "").strip() or None,
        "adopt_group_dn": str(adopt_group_dn or "").strip() or None,
        "description_text": str(description_text or "").strip() or None,
        "principal_dn": principal_dn,
        "principal_username": principal_username,
    }
    try:
        created = await create_and_publish_job(
            payload={
                "correlation_id": correlation_id,
                "job_type": "AD_ACCESS_GRANT",
                "action": "grant_ad_access",
                "status": "QUEUED",
                "identity_source_id": int(source_id),
                "storage_root_access_profile_id": int(access_profile_id or 0) or None,
                "payload_json": _job_envelope(action="grant_ad_access", payload=capsule_payload),
            },
            actor=run_provisioning_job,
        )
    except RuntimeError as exc:
        raise ProvisioningStepError("JOB_SUBMIT_FAILED", "The provisioning job could not be queued.", reason=str(exc)) from exc
    return {
        "job_id": int(created.get("job_id") or 0),
        "identity_source_id": int(source_id),
        "target_ou_dn": target_ou_dn,
        "zone_id": pctx.zone_id,
    }


@router.post("/storage-root-access-profiles/{profile_id}/adopt")
async def adopt_access_group(profile_id: int, request: Request) -> dict[str, Any]:
    """Use an existing AD group (found outside the zone OU) for this storage root level. Platform admins only."""
    require_admin(actor_from_request(request))
    payload = await request.json()
    try:
        group_dn = _canonicalize_target_ou_dn(str((payload or {}).get("group_dn") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_GROUP_DN", "message": str(exc)}) from exc
    profile = await call_route(provisioning_internal.mark_access_group_adoption, profile_id=int(profile_id), group_dn=group_dn)
    log_event(
        action="ad_group_adoption_requested",
        event_category="PROVISIONING",
        actor_type="user",
        actor_id=request.headers.get("x-identity-id"),
        entity_type="storage_root_access_profile",
        entity_id=int(profile_id),
        storage_root_id=int(profile.get("storage_root_id") or 0) or None,
        metadata_json={"group_name": profile.get("group_name"), "group_dn": group_dn},
    )
    return ui_data(profile)


async def _queue_group_membership_job(
    payload: EnsureAdGroupMemberIn | RemoveAdGroupMemberIn,
    request: Request | None,
    response: Response | None,
    *,
    job_type: str,
    action: str,
    correlation_prefix: str,
    failure_message: str,
) -> dict[str, Any]:
    correlation_id = (request.headers.get("x-request-id") if request else None) or f"{correlation_prefix}_{uuid.uuid4().hex}"

    identity_source_id = await _resolve_identity_source_id_for_group_operation(
        identity_source_id=payload.identity_source_id,
        group_ref=payload.group_ref,
    )
    capsule_ctx = await build_identity_source_capsule_context(identity_source_id, purpose="provisioning")

    capsule_payload: dict[str, Any] = {
        **capsule_ctx,
        "group_ref": str(payload.group_ref or "").strip(),
        "principal_dn": str(payload.principal_dn or "").strip() or None,
        "principal_username": str(payload.principal_username or "").strip() or None,
    }
    if payload.timeout is not None:
        capsule_payload["timeout"] = int(payload.timeout)
    if payload.verify_tls is not None:
        capsule_payload["verify_tls"] = bool(payload.verify_tls)

    try:
        created = await create_and_publish_job(
            payload={
                "correlation_id": correlation_id,
                "job_type": job_type,
                "action": action,
                "status": "QUEUED",
                "identity_source_id": int(identity_source_id),
                "payload_json": _job_envelope(action=action, payload=capsule_payload),
            },
            actor=run_provisioning_job,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error_code": str(exc), "message": failure_message},
        ) from exc

    job_id = int(created.get("job_id") or 0)
    if response is not None:
        response.status_code = status.HTTP_202_ACCEPTED
    return ui_data({
        "ok": True,
        "job_id": job_id,
        "status": "QUEUED",
        "correlation_id": correlation_id,
        "identity_source_id": int(identity_source_id),
        "group_ref": capsule_payload.get("group_ref"),
    })


async def ensure_ad_group_member(
    payload: EnsureAdGroupMemberIn,
    request: Request = None,
    response: Response = None,
):
    return await _queue_group_membership_job(
        payload,
        request,
        response,
        job_type="AD_GROUP_MEMBERSHIP",
        action="ensure_ad_group_member",
        correlation_prefix="adgm",
        failure_message="Failed to create AD group membership ensure job",
    )


async def remove_ad_group_member(
    payload: RemoveAdGroupMemberIn,
    request: Request = None,
    response: Response = None,
):
    return await _queue_group_membership_job(
        payload,
        request,
        response,
        job_type="AD_GROUP_MEMBERSHIP_REMOVE",
        action="remove_ad_group_member",
        correlation_prefix="adrm",
        failure_message="Failed to create AD group membership remove job",
    )


async def run_queued_jobs_watchdog_once(
    *,
    queued_timeout_seconds: int,
    max_republish_count: int,
    limit: int,
    correlation_id: str,
) -> dict[str, Any]:
    timeout_seconds = max(30, int(queued_timeout_seconds))
    max_republish = max(0, int(max_republish_count))
    lim = max(1, min(int(limit), 1000))

    rows = await call_route(
        provisioning_internal.list_provisioning_jobs,
        status="QUEUED",
        active_only=True,
        updated_before_seconds=timeout_seconds,
        limit=lim,
        job_type=queue_job_types_csv(),
    )
    if not isinstance(rows, list):
        rows = []

    republished: list[int] = []
    failed: list[int] = []
    skipped: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        job_id = int(row.get("id") or 0)
        if job_id <= 0:
            continue

        try:
            metrics_json = row.get("metrics_json") if isinstance(row.get("metrics_json"), dict) else {}
            republish_count = int((metrics_json or {}).get("watchdog_republish_count") or 0)
            job_type = str(row.get("job_type") or "").strip().upper()

            if republish_count < max_republish:
                await call_route(
                    provisioning_internal.mark_watchdog_republish,
                    job_id=int(job_id),
                    payload={
                        "correlation_id": correlation_id,
                        "reason": f"queued_timeout_{timeout_seconds}s",
                    },
                )
                publish_job(job_type, job_id)
                republished.append(job_id)
                continue

            await call_route(
                provisioning_internal.fail_provisioning_job,
                job_id=int(job_id),
                payload={
                    "action": row.get("action"),
                    "error_code": "JOB_QUEUED_TIMEOUT",
                    "error_message": f"Job stayed QUEUED for more than {timeout_seconds}s",
                    "result_json": {},
                    "metrics_json": metrics_json,
                    "error_json": {
                        "code": "JOB_QUEUED_TIMEOUT",
                        "message": f"Job stayed QUEUED for more than {timeout_seconds}s",
                        "watchdog": True,
                    },
                    "correlation_id": correlation_id,
                },
            )
            failed.append(job_id)
        except Exception as exc:
            skipped.append({
                "job_id": job_id,
                "error": str(exc)[:500],
            })

    return {
        "ok": True,
        "queued_timeout_seconds": timeout_seconds,
        "max_republish_count": max_republish,
        "inspected_count": len(rows),
        "republished_count": len(republished),
        "republished_job_ids": republished,
        "failed_count": len(failed),
        "failed_job_ids": failed,
        "skipped": skipped,
    }


@router.get("/admin/jobs")
async def list_admin_jobs(
    status_filter: str | None = Query(default=None, alias="status"),
    job_type: str | None = None,
    identity_source_id: int | None = None,
    storage_root_access_profile_id: int | None = None,
    active_only: bool = False,
    updated_before_seconds: int | None = None,
    limit: int = 200,
):
    rows = await call_route(
        provisioning_internal.list_provisioning_jobs,
        status=status_filter,
        job_type=job_type,
        identity_source_id=identity_source_id,
        storage_root_access_profile_id=storage_root_access_profile_id,
        active_only=active_only,
        updated_before_seconds=updated_before_seconds,
        limit=limit,
    )
    items = rows if isinstance(rows, list) else []
    return ui_list(items)


@router.post("/admin/jobs/{job_id}/cancel", dependencies=[Depends(admin_only)])
async def cancel_admin_job(job_id: int, request: Request):
    incoming = await request.json()
    payload = dict(incoming) if isinstance(incoming, dict) else {}

    correlation_id = request.headers.get("x-request-id") or f"jobcancel_{uuid.uuid4().hex}"
    requested_by = (
        request.headers.get("x-identity-id")
        or request.headers.get("x-service-name")
        or "system"
    )
    reason = str(payload.get("reason") or "Cancelled by operator").strip() or "Cancelled by operator"
    source = str(payload.get("source") or "ui").strip().lower() or "ui"

    data = await call_route(
        provisioning_internal.cancel_provisioning_job,
        job_id=int(job_id),
        payload={
            "correlation_id": correlation_id,
            "reason": reason,
            "requested_by": requested_by,
            "source": source,
        },
    )
    return ui_data(data)

