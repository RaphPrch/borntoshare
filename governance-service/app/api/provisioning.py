from __future__ import annotations

import re
import uuid
from urllib.parse import urlencode
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.dal_client import dal_get, dal_post
from app.schemas.api_envelopes import data_envelope, list_envelope
from app.shared.b2s_job_contracts.actors import publish_job, run_provisioning_job
from app.shared.b2s_job_contracts.contracts import queue_job_types_csv
from app.schemas.provisioning import (
    AccessProfileCreateIn,
    DiscoverGroupUsersRecursiveIn,
    EnsureAdGroupContextIn,
    EnsureAdGroupIn,
    EnsureAdGroupMemberIn,
    ProvisioningCompleteIn,
    RemoveAdGroupMemberIn,
)
from app.services.identity_capsule_payloads import (
    build_identity_source_capsule_context,
    infer_identity_source_id_from_group_ref,
)
from app.services.acl_engine import resolve_ntfs_rights
from app.services.audit_logger import log_event
from app.services.provisioning_context import build_provisioning_context
from app.services.provisioning_jobs import create_and_publish_job
from app.services.provisioning_naming import naming_perm
from app.services.provisioning_retry import (
    ensure_retry_attempt_allowed,
    ensure_retryable_status,
    next_retry_attempt,
    retry_backoff_minutes,
)


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


def _with_query(path: str, params: dict[str, Any] | None) -> str:
    clean: dict[str, Any] = {}
    for key, value in dict(params or {}).items():
        if value is None:
            continue
        text = str(value).strip() if isinstance(value, str) else value
        if text == "":
            continue
        clean[str(key)] = text
    if not clean:
        return path
    return f"{path}?{urlencode(clean, doseq=True)}"


def _mapping_http_status(profile_status: str) -> int:
    normalized = _normalize_job_status(profile_status)
    if normalized in {"CREATED", "QUEUED", "RUNNING", "RETRYING"}:
        return status.HTTP_202_ACCEPTED
    return status.HTTP_200_OK


def _perm_hash(level: str, rights: List[str]) -> str:
    lv = str(level or "").strip().upper()
    if lv in {"READ", "WRITE"}:
        return lv
    raise HTTPException(status_code=422, detail="access_level must be READ or WRITE")


def _normalize_access_level(value: str) -> str:
    level = str(value or "").strip().upper()
    if level not in {"READ", "WRITE"}:
        raise HTTPException(status_code=422, detail="access_level must be READ or WRITE")
    return level


def _build_access_profile_readiness(ctx: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    pctx = build_provisioning_context(ctx)

    kind = str(ctx.get("identity_source_kind") or "").strip().upper() or None
    write_enabled = bool(pctx.write_enabled)
    secret_ref = str(pctx.effective_secret_ref or "").strip()
    effective_group_ou_dn = str(pctx.effective_group_ou_dn or "").strip()

    missing_requirements: list[dict[str, str]] = []
    if kind != "AD":
        missing_requirements.append(
            {
                "code": "IDENTITY_SOURCE_NOT_AD",
                "message": "Identity source kind must be AD",
            }
        )
    if not write_enabled:
        missing_requirements.append(
            {
                "code": "WRITE_NOT_ENABLED",
                "message": "Identity source write_enabled must be true",
            }
        )
    if not secret_ref:
        missing_requirements.append(
            {
                "code": "SECRET_REF_MISSING",
                "message": "Identity source secret_ref/bind_password_ref is required",
            }
        )
    if not effective_group_ou_dn:
        missing_requirements.append(
            {
                "code": "EFFECTIVE_GROUP_OU_DN_MISSING",
                "message": "effective_group_ou_dn is missing (zone/default OU not configured)",
            }
        )

    readiness = {
        "ready": len(missing_requirements) == 0,
        "identity_source_kind": kind,
        "identity_source_id": pctx.identity_source_id,
        "zone_id": pctx.zone_id,
        "write_enabled": write_enabled,
        "has_secret_ref": bool(secret_ref),
        "secret_ref": secret_ref or None,
        "effective_group_ou_dn": effective_group_ou_dn or None,
        "missing_requirements": missing_requirements,
    }
    return pctx, readiness


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


def _extract_naming_preview_group_name(preview_payload: Any) -> str:
    preview_data = (
        preview_payload.get("data")
        if isinstance(preview_payload, dict) and isinstance(preview_payload.get("data"), dict)
        else preview_payload
    )
    if not isinstance(preview_data, dict):
        return ""

    return str(
        preview_data.get("samAccountName")
        or preview_data.get("sam_account_name")
        or preview_data.get("cn")
        or ""
    ).strip()


def _job_envelope(*, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": action,
        "payload": payload,
    }


def _job_payload_json(job: dict[str, Any] | None) -> dict[str, Any]:
    payload_json = dict((job or {}).get("payload_json") or {})
    if not isinstance(payload_json.get("payload"), dict):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_JOB_PAYLOAD_ENVELOPE",
                "message": "Provisioning job payload must be an envelope with a payload object",
            },
        )
    nested = payload_json.get("payload") if isinstance(payload_json.get("payload"), dict) else {}
    merged = dict(nested)
    merged.update(payload_json)
    return merged


def _job_payload_value(job: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    payload = _job_payload_json(job)
    value = payload.get(key)
    if value is None:
        return default
    return value


@router.get("/storage-roots/{root_id}/access-profiles/readiness")
async def get_storage_root_access_profile_readiness(root_id: int):
    ctx = await dal_get(f"/api/internal/provisioning/storage-roots/{int(root_id)}/context")
    _, readiness = _build_access_profile_readiness(ctx)
    return data_envelope({
        "storage_root_id": int(root_id),
        **readiness,
    })


async def _resolve_identity_source_id_for_group_operation(
    *,
    identity_source_id: int | None,
    group_ref: str,
) -> int:
    resolved_id = int(identity_source_id or 0) or None
    if resolved_id:
        return int(resolved_id)
    return int(await infer_identity_source_id_from_group_ref(group_ref))


@router.post("/ad-groups/ensure-via-name")
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
    profile_id = int((payload.context.access_profile_id if payload.context else 0) or 0) or None
    resolved_host = str(payload.directory_server_hint or "").strip() or None
    resolved_port: int | None = None
    resolved_protocol: str | None = None
    resolved_bind_dn: str | None = None

    if root_id > 0:
        ctx = await dal_get(f"/api/internal/provisioning/storage-roots/{root_id}/context")
        pctx = build_provisioning_context(ctx)

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

    if profile_id:
        existing_job = None
        try:
            existing_job = await dal_get(f"/api/internal/provisioning/jobs/by-profile/{int(profile_id)}")
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

        if isinstance(existing_job, dict):
            existing_status = _normalize_job_status(str(existing_job.get("status") or "QUEUED"))
            if existing_status in {"QUEUED", "RUNNING", "RETRYING"}:
                if response is not None:
                    response.status_code = status.HTTP_202_ACCEPTED
                return data_envelope({
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
                    "description_text": payload.description_text,
                    "domain_name": domain_name,
                    "secret_ref": secret_ref,
                    "context": {
                        "storage_root_id": root_id or None,
                        "access_profile_id": profile_id,
                        "zone_id": int((payload.context.zone_id if payload.context else 0) or 0) or None,
                        "correlation_id": correlation_id,
                    },
                    },
                ),
            },
            dal_post_fn=dal_post,
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

    return data_envelope({
        "ok": True,
        "job_id": job_id,
        "status": "QUEUED",
        "correlation_id": correlation_id,
        "group_name": group_name,
        "target_ou_dn": target_ou_dn,
    })


@router.post("/ad-groups/members/ensure")
async def ensure_ad_group_member(
    payload: EnsureAdGroupMemberIn,
    request: Request = None,
    response: Response = None,
):
    correlation_id = (request.headers.get("x-request-id") if request else None) or f"adgm_{uuid.uuid4().hex}"

    identity_source_id = await _resolve_identity_source_id_for_group_operation(
        identity_source_id=payload.identity_source_id,
        group_ref=payload.group_ref,
    )
    capsule_ctx = await build_identity_source_capsule_context(identity_source_id)

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
                "job_type": "AD_GROUP_MEMBERSHIP",
                "action": "ensure_ad_group_member",
                "status": "QUEUED",
                "identity_source_id": int(identity_source_id),
                "payload_json": _job_envelope(
                    action="ensure_ad_group_member",
                    payload=capsule_payload,
                ),
            },
            dal_post_fn=dal_post,
            actor=run_provisioning_job,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error_code": str(exc), "message": "Failed to create AD group membership ensure job"},
        ) from exc

    job_id = int(created.get("job_id") or 0)
    if response is not None:
        response.status_code = status.HTTP_202_ACCEPTED
    return data_envelope({
        "ok": True,
        "job_id": job_id,
        "status": "QUEUED",
        "correlation_id": correlation_id,
        "identity_source_id": int(identity_source_id),
        "group_ref": capsule_payload.get("group_ref"),
    })


@router.post("/ad-groups/members/remove")
async def remove_ad_group_member(
    payload: RemoveAdGroupMemberIn,
    request: Request = None,
    response: Response = None,
):
    correlation_id = (request.headers.get("x-request-id") if request else None) or f"adrm_{uuid.uuid4().hex}"

    identity_source_id = await _resolve_identity_source_id_for_group_operation(
        identity_source_id=payload.identity_source_id,
        group_ref=payload.group_ref,
    )
    capsule_ctx = await build_identity_source_capsule_context(identity_source_id)

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
                "job_type": "AD_GROUP_MEMBERSHIP_REMOVE",
                "action": "remove_ad_group_member",
                "status": "QUEUED",
                "identity_source_id": int(identity_source_id),
                "payload_json": _job_envelope(
                    action="remove_ad_group_member",
                    payload=capsule_payload,
                ),
            },
            dal_post_fn=dal_post,
            actor=run_provisioning_job,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error_code": str(exc), "message": "Failed to create AD group membership remove job"},
        ) from exc

    job_id = int(created.get("job_id") or 0)
    if response is not None:
        response.status_code = status.HTTP_202_ACCEPTED
    return data_envelope({
        "ok": True,
        "job_id": job_id,
        "status": "QUEUED",
        "correlation_id": correlation_id,
        "identity_source_id": int(identity_source_id),
        "group_ref": capsule_payload.get("group_ref"),
    })


@router.post("/ad-groups/members/discover-recursive")
async def discover_ad_group_users_recursive(
    payload: DiscoverGroupUsersRecursiveIn,
    request: Request = None,
    response: Response = None,
):
    correlation_id = (request.headers.get("x-request-id") if request else None) or f"adgr_{uuid.uuid4().hex}"

    identity_source_id = await _resolve_identity_source_id_for_group_operation(
        identity_source_id=payload.identity_source_id,
        group_ref=payload.root_group_dn,
    )
    capsule_ctx = await build_identity_source_capsule_context(identity_source_id)

    capsule_payload: dict[str, Any] = {
        **capsule_ctx,
        "root_group_dn": str(payload.root_group_dn or "").strip(),
        "max_depth": int(payload.max_depth),
    }
    if payload.timeout is not None:
        capsule_payload["timeout"] = int(payload.timeout)
    if payload.verify_tls is not None:
        capsule_payload["verify_tls"] = bool(payload.verify_tls)

    try:
        created = await create_and_publish_job(
            payload={
                "correlation_id": correlation_id,
                "job_type": "GROUP_USERS_DISCOVERY",
                "action": "discover_group_users_recursive",
                "status": "QUEUED",
                "identity_source_id": int(identity_source_id),
                "payload_json": _job_envelope(
                    action="discover_group_users_recursive",
                    payload=capsule_payload,
                ),
            },
            dal_post_fn=dal_post,
            actor=run_provisioning_job,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error_code": str(exc), "message": "Failed to create recursive group users discovery job"},
        ) from exc

    job_id = int(created.get("job_id") or 0)
    if response is not None:
        response.status_code = status.HTTP_202_ACCEPTED
    return data_envelope({
        "ok": True,
        "job_id": job_id,
        "status": "QUEUED",
        "correlation_id": correlation_id,
        "identity_source_id": int(identity_source_id),
        "root_group_dn": capsule_payload.get("root_group_dn"),
    })


@router.post("/storage-roots/{root_id}/access-profiles")
async def create_storage_root_access_profile(
    root_id: int,
    payload: AccessProfileCreateIn,
    request: Request = None,
    response: Response = None,
):
    ctx = await dal_get(f"/api/internal/provisioning/storage-roots/{int(root_id)}/context")
    actor_id = (
        (request.headers.get("x-identity-id") if request else None)
        or (request.headers.get("x-service-name") if request else None)
        or "system"
    )
    correlation_id = (request.headers.get("x-request-id") if request else None) or f"prov_{uuid.uuid4().hex}"
    actor_ip, user_agent = _request_actor_context(request)

    pctx, readiness = _build_access_profile_readiness(ctx)
    if not bool(readiness.get("ready")):
        missing = readiness.get("missing_requirements") if isinstance(readiness, dict) else []
        message = "Access profile attach prerequisites are not satisfied"
        if isinstance(missing, list) and missing:
            first = missing[0] if isinstance(missing[0], dict) else {}
            candidate = str(first.get("message") or "").strip()
            if candidate:
                message = candidate
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "ACCESS_PROFILE_ATTACH_NOT_READY",
                "message": message,
                "details": {
                    "storage_root_id": int(root_id),
                    **readiness,
                },
            },
        )

    secret_ref = str(readiness.get("secret_ref") or "").strip()

    level = _normalize_access_level(payload.access_level)

    effective_group_ou_dn = str(readiness.get("effective_group_ou_dn") or "").strip()
    try:
        target_ou_dn = _canonicalize_target_ou_dn(effective_group_ou_dn)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_TARGET_OU_DN",
                "message": "effective_group_ou_dn is invalid",
                "hint": "Expected LDAP DN, e.g. OU=Groups,DC=corp,DC=local",
                "reason": str(exc),
                "target_ou_dn": effective_group_ou_dn or None,
                "storage_root_id": int(root_id),
            },
        ) from exc

    existing = await dal_get(
        f"/api/internal/provisioning/storage-root-access-profiles?storage_root_id={int(root_id)}&access_level_code={level}",
        timeout=5,
    )
    if not isinstance(existing, list):
        existing = []
    for row in existing:
        if int(row.get("storage_root_id") or 0) != int(root_id):
            continue
        if str(row.get("access_level_code") or "").strip().upper() != level:
            continue
        existing_status = _normalize_job_status(str(row.get("status") or "QUEUED"))
        body = {
            "id": int(row.get("id") or 0),
            "access_level": level,
            "status": existing_status,
            "members_count": int(row.get("members_count") or 0),
            "updated_at": row.get("updated_at"),
            "last_error_message": str(row.get("error_message") or "").strip() or None,
        }
        if response is not None:
            response.status_code = _mapping_http_status(existing_status)
        return data_envelope(body)

    preview = await dal_post(
        "/api/naming-policies/preview",
        {
            "zone_id": str(ctx.get("zone_id") or ""),
            "storage_root_path": str(ctx.get("root_path") or ""),
            "storage_root_id": int(root_id),
            "storage_endpoint_id": int(ctx.get("storage_endpoint_id") or 0) or None,
            "perm": naming_perm(level),
            "profile": level,
        },
    )
    group_name = _extract_naming_preview_group_name(preview)
    if not group_name:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NAMING_PREVIEW_EMPTY",
                "message": "Unable to compute group name from naming preview",
                "details": {
                    "storage_root_id": int(root_id),
                    "zone_id": int(ctx.get("zone_id") or 0) or None,
                    "access_level": level,
                },
            },
        )

    permission_hash = _perm_hash(level=level, rights=payload.rights or [])

    _ = resolve_ntfs_rights(level, permission_hash)

    upsert = await dal_post(
        "/api/internal/provisioning/storage-root-access-profiles",
        {
            "storage_root_id": int(root_id),
            "access_level_code": level,
            "permission_hash": permission_hash,
            "group_name": group_name,
            "name": f"{level} profile",
            "status": "CREATED",
            "actor_ip": actor_ip,
            "user_agent": user_agent,
            "correlation_id": correlation_id,
        },
    )

    ap = (upsert or {}).get("data") or {}
    profile_id = int(ap.get("id") or 0)
    if profile_id <= 0:
        raise HTTPException(status_code=500, detail="Failed to create access profile")

    if (upsert or {}).get("created") is True:
        log_event(
            action="access_profile_created",
            event_category="ACCESS_PROFILE",
            event_scope="business",
            actor_type="user" if str(actor_id).isdigit() else "service",
            actor_id=actor_id,
            entity_type="access_profile",
            entity_id=profile_id,
            zone_id=int(ctx.get("zone_id") or 0) or None,
            storage_root_id=int(root_id),
            correlation_id=correlation_id,
            result="success",
            severity="info",
            metadata_json={
                "before": None,
                "after": {
                    "access_level_code": level,
                    "status": str(ap.get("status") or "CREATED"),
                },
                "details": "Access profile row created by governance",
            },
            actor_ip=actor_ip,
            user_agent=user_agent,
        )

    if (upsert or {}).get("created") is False:
        existing_status = _normalize_job_status(str(ap.get("status") or "QUEUED"))
        if response is not None:
            response.status_code = _mapping_http_status(existing_status)
        return data_envelope({
            "id": profile_id,
            "access_level": str(ap.get("access_level_code") or level),
            "status": existing_status,
            "members_count": 0,
            "updated_at": ap.get("updated_at"),
            "last_error_message": str(ap.get("error_message") or "").strip() or None,
        })

    await dal_post(
        f"/api/internal/provisioning/storage-root-access-profiles/{profile_id}/queue",
        {
            "correlation_id": correlation_id,
            "actor_ip": actor_ip,
            "user_agent": user_agent,
        },
    )

    log_event(
        action="access_profile_provisioning_started",
        event_category="PROVISIONING",
        event_scope="business",
        actor_type="user" if str(actor_id).isdigit() else "service",
        actor_id=actor_id,
        entity_type="access_profile",
        entity_id=profile_id,
        zone_id=int(ctx.get("zone_id") or 0) or None,
        storage_root_id=int(root_id),
        correlation_id=correlation_id,
        result="in_progress",
        severity="info",
        metadata_json={
            "before": {"status": str(ap.get("status") or "CREATED")},
            "after": {"status": "QUEUED"},
            "details": {"stage": "AD_GROUP_ENSURE", "job_type": "AD_GROUP_ENSURE"},
        },
        actor_ip=actor_ip,
        user_agent=user_agent,
    )

    existing_job = None
    try:
        existing_job = await dal_get(f"/api/internal/provisioning/jobs/by-profile/{profile_id}")
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise
    if isinstance(existing_job, dict):
        existing_job_status = _normalize_job_status(str(existing_job.get("status") or "QUEUED"))
        if existing_job_status in {"QUEUED", "RUNNING"}:
            if response is not None:
                response.status_code = status.HTTP_202_ACCEPTED
            return data_envelope({
                "id": profile_id,
                "access_level": level,
                "status": existing_job_status,
                "members_count": 0,
                "updated_at": existing_job.get("updated_at"),
                "last_error_message": str(existing_job.get("error_message") or "").strip() or None,
                "correlation_id": existing_job.get("correlation_id"),
            })

    try:
        _ = await create_and_publish_job(
            payload={
                "correlation_id": correlation_id,
                "job_type": "AD_GROUP_ENSURE",
                "action": "ensure_ad_group",
                "status": "QUEUED",
                "storage_root_access_profile_id": profile_id,
                "identity_source_id": pctx.identity_source_id,
                "payload_json": _job_envelope(
                    action="ensure_ad_group",
                    payload={
                    "template": {"slug": "ensure_ad_group", "version": "v1"},
                    "storage_root_id": int(root_id),
                    "zone_id": pctx.zone_id,
                    "storage_endpoint_id": int(ctx.get("storage_endpoint_id") or 0) or None,
                    "identity_source_id": pctx.identity_source_id,
                    "group_name": group_name,
                    "target_ou_dn": target_ou_dn,
                    "effective_group_ou_dn": target_ou_dn,
                    "default_group_ou_dn": ctx.get("default_group_ou_dn"),
                    "domain_name": pctx.domain_name,
                    "secret_ref": secret_ref,
                    "access_level_code": level,
                    "identity_source": {
                        "id": pctx.identity_source_id,
                        "kind": ctx.get("identity_source_kind"),
                        "host": pctx.resolved_host,
                        "port": pctx.resolved_port,
                        "protocol": pctx.resolved_protocol,
                        "bind_dn": pctx.resolved_bind_dn,
                        "base_dn": ctx.get("identity_source_base_dn"),
                        "domain_name": pctx.domain_name,
                        "secret_ref": secret_ref,
                    },
                    },
                ),
            },
            dal_post_fn=dal_post,
            actor=run_provisioning_job,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error_code": str(exc), "message": "Failed to create provisioning job"},
        ) from exc

    if response is not None:
        response.status_code = status.HTTP_202_ACCEPTED

    return data_envelope({
        "id": profile_id,
        "access_level": level,
        "status": "QUEUED",
        "members_count": 0,
        "updated_at": ap.get("updated_at"),
        "last_error_message": None,
        "correlation_id": correlation_id,
    })


@router.post("/api/provisioning/jobs/{correlation_id}/complete")
async def complete_provisioning_job(
    correlation_id: str,
    payload: ProvisioningCompleteIn,
    request: Request = None,
):
    job = await dal_get(f"/api/internal/provisioning/jobs/by-correlation/{correlation_id}")
    if not job:
        raise HTTPException(status_code=404, detail="Provisioning job not found")
    actor_id = (
        (request.headers.get("x-identity-id") if request else None)
        or (request.headers.get("x-service-name") if request else None)
        or "system"
    )
    actor_ip, user_agent = _request_actor_context(request)

    stage = str(payload.stage or "").upper()
    outcome = str(payload.status or "").upper()
    success = outcome in {"SUCCESS", "OK", "DONE", "SUCCEEDED"}

    profile_id = int(job.get("storage_root_access_profile_id") or 0)
    if profile_id <= 0:
        if success:
            await dal_post(
                f"/api/internal/provisioning/jobs/{int(job.get('id'))}/complete",
                {
                    "result_json": payload.result_json,
                    "actor_ip": actor_ip,
                    "user_agent": user_agent,
                    "correlation_id": correlation_id,
                },
            )
        else:
            await dal_post(
                f"/api/internal/provisioning/jobs/{int(job.get('id'))}/fail",
                {
                    "error_code": payload.error_code or "RUN_JOB_FAILED",
                    "error_message": payload.error_message,
                    "result_json": payload.result_json,
                    "actor_ip": actor_ip,
                    "user_agent": user_agent,
                    "correlation_id": correlation_id,
                },
            )
        return data_envelope({"ok": True})

    if stage == "AD_GROUP_ENSURE":
        # Enforce strict envelope contract before writing completion side-effects.
        _ = _job_payload_json(job)
        await dal_post(
            f"/api/internal/provisioning/jobs/{int(job.get('id'))}/complete-and-apply",
            {
                "outcome": "SUCCEEDED" if success else "FAILED",
                "result_json": payload.result_json,
                "error_code": None if success else (payload.error_code or "RUN_JOB_FAILED"),
                "error_message": None if success else payload.error_message,
                "profile_id": profile_id,
                "group_external_id": (payload.group_dn or payload.group_external_id) if success else None,
                "event_type": "profile_provisioning_success" if success else "profile_provisioning_failed",
                "event_payload_json": {
                    "stage": stage,
                    "group_external_id": payload.group_external_id,
                    "group_dn": payload.group_dn,
                },
                "actor_ip": actor_ip,
                "user_agent": user_agent,
                "correlation_id": correlation_id,
            },
        )

        if not success:
            log_event(
                action="access_profile_provisioning_failed",
                event_category="PROVISIONING",
                event_scope="business",
                actor_type="user" if str(actor_id).isdigit() else "service",
                actor_id=actor_id,
                entity_type="access_profile",
                entity_id=profile_id,
                zone_id=int(_job_payload_value(job, "zone_id", 0) or 0) or None,
                storage_root_id=int(_job_payload_value(job, "storage_root_id", 0) or 0) or None,
                correlation_id=correlation_id,
                result="failure",
                severity="error",
                metadata_json={
                    "before": {"status": "RUNNING"},
                    "after": {"status": "RETRYING_OR_FAILED"},
                    "details": {
                        "stage": stage,
                        "error_code": payload.error_code,
                        "error_message": payload.error_message,
                    },
                },
                actor_ip=actor_ip,
                user_agent=user_agent,
            )
            return data_envelope({"ok": True})
        log_event(
            action="access_profile_provisioning_succeeded",
            event_category="PROVISIONING",
            event_scope="business",
            actor_type="user" if str(actor_id).isdigit() else "service",
            actor_id=actor_id,
            entity_type="access_profile",
            entity_id=profile_id,
            zone_id=int(_job_payload_value(job, "zone_id", 0) or 0) or None,
            storage_root_id=int(_job_payload_value(job, "storage_root_id", 0) or 0) or None,
            correlation_id=correlation_id,
            result="success",
            severity="info",
            metadata_json={
                "before": {"status": "RUNNING"},
                "after": {
                    "status": "SUCCEEDED",
                    "group_external_id": payload.group_external_id,
                    "group_dn": payload.group_dn,
                },
                "details": {"stage": stage},
            },
            actor_ip=actor_ip,
            user_agent=user_agent,
        )
        return data_envelope({"ok": True})

    return data_envelope({"ok": True})


@router.post("/api/provisioning/jobs/{correlation_id}/retry")
async def retry_failed_provisioning_job(
    correlation_id: str,
    request: Request = None,
):
    job = await dal_get(f"/api/internal/provisioning/jobs/by-correlation/{correlation_id}")
    if not job:
        raise HTTPException(status_code=404, detail="Provisioning job not found")

    current_status = _normalize_job_status(str(job.get("status") or ""))
    ensure_retryable_status(current_status)

    profile_id = int(job.get("storage_root_access_profile_id") or 0)
    if profile_id <= 0:
        raise HTTPException(status_code=422, detail="Provisioning job is not linked to a storage root access profile")

    profile = await dal_get(f"/api/internal/provisioning/storage-root-access-profiles/{profile_id}")
    if not isinstance(profile, dict):
        raise HTTPException(status_code=404, detail="Storage root access profile not found")

    root_id = int(_job_payload_value(job, "storage_root_id", 0) or 0)
    if root_id <= 0:
        raise HTTPException(status_code=422, detail="Provisioning job payload is missing storage_root_id")

    ctx = await dal_get(f"/api/internal/provisioning/storage-roots/{int(root_id)}/context")
    pctx = build_provisioning_context(ctx)

    effective_group_ou_dn = pctx.effective_group_ou_dn
    if not effective_group_ou_dn:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provisioning refused: effective_group_ou_dn is missing (zone/default OU not configured)",
        )
    try:
        target_ou_dn = _canonicalize_target_ou_dn(effective_group_ou_dn)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_TARGET_OU_DN",
                "message": "Cannot retry: invalid effective_group_ou_dn",
                "reason": str(exc),
                "target_ou_dn": str(effective_group_ou_dn or "").strip() or None,
                "storage_root_id": int(root_id),
            },
        ) from exc

    payload_json = dict(job.get("payload_json") or {})
    group_name = str(_job_payload_value(job, "group_name", "") or "").strip()
    secret_ref = str(pctx.effective_secret_ref or "").strip()
    if not group_name or not secret_ref:
        raise HTTPException(status_code=422, detail="Cannot retry: missing provisioning payload group_name/secret_ref")
    payload_json["target_ou_dn"] = target_ou_dn
    payload_json["effective_group_ou_dn"] = target_ou_dn
    payload_json["secret_ref"] = secret_ref
    if isinstance(payload_json.get("payload"), dict):
        payload_json["payload"]["target_ou_dn"] = target_ou_dn
        payload_json["payload"]["effective_group_ou_dn"] = target_ou_dn
        payload_json["payload"]["secret_ref"] = secret_ref

    actor_id = (
        (request.headers.get("x-identity-id") if request else None)
        or (request.headers.get("x-service-name") if request else None)
        or "system"
    )
    actor_ip, user_agent = _request_actor_context(request)

    next_attempt = next_retry_attempt(job.get("attempt_count"), (profile or {}).get("attempt_count"))
    ensure_retry_attempt_allowed(next_attempt)
    backoff_minutes = retry_backoff_minutes(next_attempt)
    retry_correlation_id = f"{correlation_id}-retry-{next_attempt}"

    try:
        created = await create_and_publish_job(
            payload={
                "correlation_id": retry_correlation_id,
                "job_type": str(job.get("job_type") or "AD_GROUP_ENSURE"),
                "action": str(job.get("action") or "ensure_ad_group"),
                "status": "QUEUED",
                "storage_root_access_profile_id": profile_id,
                "identity_source_id": int(job.get("identity_source_id") or 0) or None,
                "payload_json": payload_json,
                "metrics_json": {
                    "retry_attempt": next_attempt,
                    "retry_backoff_minutes": backoff_minutes,
                    "source_job_attempt": int(job.get("attempt_count") or 0),
                    "source_profile_attempt": int((profile or {}).get("attempt_count") or 0),
                },
            },
            dal_post_fn=dal_post,
            actor=run_provisioning_job,
        )
        new_job_id = int(created.get("job_id") or 0)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error_code": str(exc), "message": "Failed to create retry provisioning job"},
        ) from exc

    log_event(
        action="access_profile_provisioning_retry",
        event_category="PROVISIONING",
        event_scope="business",
        actor_type="user" if str(actor_id).isdigit() else "service",
        actor_id=actor_id,
        entity_type="access_profile",
        entity_id=profile_id,
        zone_id=pctx.zone_id,
        storage_root_id=int(root_id),
        correlation_id=correlation_id,
        result="in_progress",
        severity="info",
        metadata_json={
            "before": {"status": current_status},
            "after": {"status": "QUEUED"},
            "details": {
                "action": "retry",
                "new_job_id": new_job_id,
                "next_attempt": next_attempt,
                "backoff_minutes": backoff_minutes,
                "source_job_attempt": int(job.get("attempt_count") or 0),
                "source_profile_attempt": int((profile or {}).get("attempt_count") or 0),
            },
        },
        actor_ip=actor_ip,
        user_agent=user_agent,
    )

    return data_envelope({
        "ok": True,
        "correlation_id": retry_correlation_id,
        "status": "QUEUED",
        "attempt_count": next_attempt,
        "backoff_minutes": backoff_minutes,
    })


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

    rows = await dal_get(
        _with_query(
            "/api/internal/provisioning/jobs",
            {
                "status": "QUEUED",
                "active_only": "true",
                "updated_before_seconds": timeout_seconds,
                "limit": lim,
                "job_type": queue_job_types_csv(),
            },
        )
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
                await dal_post(
                    f"/api/internal/provisioning/jobs/{job_id}/watchdog-republish-mark",
                    {
                        "correlation_id": correlation_id,
                        "reason": f"queued_timeout_{timeout_seconds}s",
                    },
                )
                publish_job(job_type, job_id)
                republished.append(job_id)
                continue

            await dal_post(
                f"/api/internal/provisioning/jobs/{job_id}/fail",
                {
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
async def list_admin_jobs(request: Request):
    rows = await dal_get(
        _with_query(
            "/api/internal/provisioning/jobs",
            dict(request.query_params),
        )
    )
    items = rows if isinstance(rows, list) else []
    return list_envelope(items)


@router.post("/admin/jobs/{job_id}/cancel")
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

    data = await dal_post(
        f"/api/internal/provisioning/jobs/{int(job_id)}/cancel",
        {
            "correlation_id": correlation_id,
            "reason": reason,
            "requested_by": requested_by,
            "source": source,
        },
    )
    return data_envelope(data)


@router.post("/admin/jobs/watchdog/run")
async def run_admin_jobs_watchdog(request: Request):
    incoming = await request.json()
    payload = dict(incoming) if isinstance(incoming, dict) else {}
    correlation_id = request.headers.get("x-request-id") or f"jobwatchdog_{uuid.uuid4().hex}"

    result = await run_queued_jobs_watchdog_once(
        queued_timeout_seconds=int(payload.get("queued_timeout_seconds") or 300),
        max_republish_count=int(payload.get("max_republish_count") or 1),
        limit=int(payload.get("limit") or 200),
        correlation_id=correlation_id,
    )
    return data_envelope(result)


@router.post("/internal/provisioning/reconcile")
async def reconcile_provisioning_jobs(request: Request = None):
    correlation_id = (request.headers.get("x-request-id") if request else None) or f"prov_{uuid.uuid4().hex}"
    actor_ip, user_agent = _request_actor_context(request)

    rows = await dal_get("/api/internal/provisioning/reconcile-candidates?limit=200")
    if not isinstance(rows, list):
        rows = []

    requeued: list[int] = []
    skipped: list[dict] = []
    for row in rows:
        try:
            job_id = int((row or {}).get("job_id") or 0)
            profile_id = int((row or {}).get("storage_root_access_profile_id") or 0)
            if job_id <= 0 or profile_id <= 0:
                continue

            await dal_post(
                f"/api/internal/provisioning/jobs/{job_id}/requeue",
                {
                    "correlation_id": correlation_id,
                    "reason": "reconcile",
                    "force": True,
                },
            )
            publish_job(str((row or {}).get("job_type") or ""), job_id)
            requeued.append(job_id)
        except Exception as exc:
            skipped.append({"row": row, "error": str(exc)})

    log_event(
        action="access_profile_provisioning_reconcile",
        event_category="PROVISIONING",
        event_scope="technical",
        actor_type="service",
        actor_id="governance",
        entity_type="provisioning_job",
        entity_id=None,
        correlation_id=correlation_id,
        result="success",
        severity="info",
        metadata_json={
            "requeued_jobs": requeued,
            "requeued_count": len(requeued),
            "skipped_count": len(skipped),
        },
        actor_ip=actor_ip,
        user_agent=user_agent,
    )

    return data_envelope({
        "ok": True,
        "requeued_count": len(requeued),
        "requeued_jobs": requeued,
        "skipped": skipped,
    })
