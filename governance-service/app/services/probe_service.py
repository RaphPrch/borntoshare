from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException, status

from app.core.dal_client import dal_get, dal_post
from app.core.logging import get_logger
from app.services.job_run_service import build_job_run_data
from app.shared.b2s_job_contracts.actors import publish_job


logger = get_logger("gov-probe-service")


_PROBE_JOB_TYPE_BY_TEMPLATE = {
    "test_smb_ntlm": "SMB_PROBE",
    "test_smb_root_access": "SMB_PROBE",
    "test_ldap": "LDAP_TEST",
    "test_ldaps": "LDAP_TEST",
    "search_ldap_principals": "IDENTITY_SEARCH",
    "search_ldaps_principals": "IDENTITY_SEARCH",
    "acl_apply_via_group": "ACL_APPLY",
}


def _as_int(value: Any) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_acl_permission(value: Any) -> str | None:
    raw = str(value or "").strip().upper()
    if raw in {"READ", "R"}:
        return "read"
    if raw in {"WRITE", "W", "MODIFY", "FULL", "FULL_CONTROL", "RW"}:
        return "write"
    if raw == "AUDIT":
        return "audit"
    return None


def _parse_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _target_key(template_slug: str, target: dict[str, Any], context: dict[str, Any]) -> tuple[str, int | str] | None:
    if template_slug == "test_smb_root_access":
        root_id = _as_int(target.get("storage_root_id")) or _as_int(context.get("storage_root_id"))
        return ("storage_root_id", int(root_id)) if root_id else None
    if template_slug == "test_smb_ntlm":
        endpoint_id = _as_int(target.get("storage_endpoint_id")) or _as_int(context.get("storage_endpoint_id"))
        if endpoint_id:
            return ("storage_endpoint_id", int(endpoint_id))
        host = str(target.get("host") or "").strip().lower()
        return ("host", host) if host else None
    if template_slug in {"test_ldap", "test_ldaps", "search_ldap_principals", "search_ldaps_principals"}:
        source_id = _as_int(context.get("identity_source_id")) or _as_int(target.get("identity_source_id"))
        return ("identity_source_id", int(source_id)) if source_id else None
    return None


def _payload_matches_probe_target(
    *,
    row: dict[str, Any],
    template_slug: str,
    target_key: tuple[str, int | str] | None,
) -> bool:
    if str(row.get("action") or "").strip() != template_slug:
        return False
    if not target_key:
        return False

    payload_json = row.get("payload_json")
    if isinstance(payload_json, str):
        try:
            payload_json = json.loads(payload_json)
        except ValueError:
            payload_json = {}
    if not isinstance(payload_json, dict):
        return False
    payload = payload_json.get("payload") if isinstance(payload_json.get("payload"), dict) else {}
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}

    key, expected = target_key
    if key == "host":
        actual = str(target.get("host") or "").strip().lower()
        return actual == str(expected)
    actual = _as_int(target.get(key)) or _as_int(context.get(key))
    return actual == int(expected)


def _job_age_seconds(row: dict[str, Any]) -> int:
    started = _parse_dt(row.get("started_at"))
    created = _parse_dt(row.get("created_at"))
    anchor = started or created
    if not anchor:
        return 0
    return max(0, int((datetime.now(timezone.utc) - anchor).total_seconds()))


def _probe_timeout_seconds(row: dict[str, Any], *, fallback: int = 30) -> int:
    payload_json = row.get("payload_json")
    if isinstance(payload_json, str):
        try:
            payload_json = json.loads(payload_json)
        except ValueError:
            payload_json = {}
    if not isinstance(payload_json, dict):
        return fallback
    payload = payload_json.get("payload") if isinstance(payload_json.get("payload"), dict) else {}
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    try:
        timeout_sec = int(options.get("timeout_sec") or fallback)
    except (TypeError, ValueError):
        timeout_sec = fallback
    return max(1, timeout_sec)


async def _find_equivalent_active_probe(
    *,
    template_slug: str,
    job_type: str,
    target: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any] | None:
    target_key = _target_key(template_slug, target, context)
    if not target_key:
        return None

    rows = await dal_get(
        f"/api/internal/provisioning/jobs?job_type={job_type}&active_only=true&limit=100",
        timeout=5,
    )
    if not isinstance(rows, list):
        return None

    for row in rows:
        if not isinstance(row, dict):
            continue
        if _payload_matches_probe_target(row=row, template_slug=template_slug, target_key=target_key):
            return row
    return None


async def _fail_stale_probe_job(row: dict[str, Any], *, template_slug: str, max_age_seconds: int) -> None:
    job_id = _as_int(row.get("id"))
    if not job_id:
        return
    await dal_post(
        f"/api/internal/provisioning/jobs/{int(job_id)}/fail",
        {
            "action": template_slug,
            "error_code": "PROBE_JOB_TIMEOUT",
            "error_message": f"Probe job exceeded {int(max_age_seconds)} seconds",
            "result_json": {
                "success": False,
                "message": "Probe job timed out",
                "details": {
                    "failure_code": "PROBE_JOB_TIMEOUT",
                    "checks": [
                        {
                            "name": "probe_execution",
                            "status": "failed",
                            "message": f"Probe job exceeded {int(max_age_seconds)} seconds",
                        }
                    ],
                },
            },
            "correlation_id": f"probe_timeout_{uuid.uuid4().hex}",
        },
        timeout=8,
    )


def _parse_unc_root_path(value: Any) -> tuple[str, str, str]:
    raw = str(value or "").strip()
    if not raw:
        return "", "", ""

    normalized = raw.replace("/", "\\")
    parts = [chunk for chunk in normalized.split("\\") if chunk]
    if len(parts) < 2:
        return "", "", ""

    host = parts[0]
    share = parts[1]
    rel_path = "/".join(parts[2:]).strip("/")
    return host, share, rel_path


async def _resolve_profile_row(
    *,
    storage_root_id: int,
    access_level_code: str | None,
    access_profile_id: int | None,
) -> dict[str, Any] | None:
    path = f"/api/internal/provisioning/storage-root-access-profiles?storage_root_id={int(storage_root_id)}"
    if access_level_code:
        path += f"&access_level_code={quote(access_level_code)}"

    rows = await dal_get(path, timeout=5)
    if not isinstance(rows, list):
        return None

    if access_profile_id:
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_profile_id = _as_int(row.get("access_profile_id"))
            row_link_id = _as_int(row.get("id"))
            if access_profile_id in {row_profile_id, row_link_id}:
                return row

    for row in rows:
        if isinstance(row, dict):
            return row
    return None


async def _enrich_acl_probe_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    target = dict(payload.get("target") or {})
    auth = dict(payload.get("auth") or {})
    options = dict(payload.get("options") or {})
    context = dict(payload.get("context") or {})

    storage_root_id = _as_int(target.get("storage_root_id")) or _as_int(context.get("storage_root_id"))
    if not storage_root_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "PROBE_ACL_CONTEXT_REQUIRED",
                "message": "ACL probe requires target.storage_root_id",
                "missing_fields": ["target.storage_root_id"],
            },
        )

    ctx = await dal_get(f"/api/internal/provisioning/storage-roots/{int(storage_root_id)}/context", timeout=5)
    if not isinstance(ctx, dict):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "PROBE_ACL_CONTEXT_NOT_FOUND",
                "message": "Storage root provisioning context not found",
                "storage_root_id": int(storage_root_id),
            },
        )

    access_profile_id = _as_int(target.get("access_profile_id"))
    raw_level = str(target.get("access_level_code") or "").strip().upper() or None
    profile_row = await _resolve_profile_row(
        storage_root_id=int(storage_root_id),
        access_level_code=raw_level,
        access_profile_id=access_profile_id,
    )

    resolved_level = raw_level or (
        str((profile_row or {}).get("access_level_code") or "").strip().upper() if profile_row else None
    )
    permission = _normalize_acl_permission(target.get("permission") or resolved_level)

    host = str(target.get("host") or "").strip()
    share = str(target.get("share") or "").strip()
    rel_path = str(target.get("path") or "").strip().strip("/\\")

    parsed_host, parsed_share, parsed_rel = _parse_unc_root_path(ctx.get("root_path"))
    host = host or parsed_host or str(ctx.get("host") or "").strip()
    share = share or parsed_share
    if not rel_path:
        rel_path = parsed_rel

    group_name = str(target.get("group_name") or target.get("ad_group_name") or "").strip()
    if not group_name and profile_row:
        group_name = str(profile_row.get("group_name") or profile_row.get("ad_group_name") or "").strip()

    username = str(
        auth.get("username")
        or auth.get("bind_dn")
        or ctx.get("endpoint_bind_dn")
        or ctx.get("identity_source_bind_dn")
        or ""
    ).strip()
    secret_ref = str(
        auth.get("secret_ref")
        or ctx.get("endpoint_bind_password_ref")
        or ctx.get("identity_source_bind_password_ref")
        or ctx.get("secret_ref")
        or ""
    ).strip()
    domain_name = str(auth.get("domain") or ctx.get("domain_name") or "").strip()

    missing_fields: list[str] = []
    if not host:
        missing_fields.append("host")
    if not share:
        missing_fields.append("share")
    if not group_name:
        missing_fields.append("group_name")
    if not permission:
        missing_fields.append("permission")
    if not username:
        missing_fields.append("username")
    if not secret_ref:
        missing_fields.append("secret_ref")

    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "PROBE_ACL_INPUT_MISSING",
                "message": "Unable to build ACL probe payload from storage root context",
                "storage_root_id": int(storage_root_id),
                "missing_fields": missing_fields,
            },
        )

    target.update(
        {
            "host": host,
            "share": share,
            "path": rel_path,
            "group_name": group_name,
            "ad_group_name": group_name,
            "permission": permission,
        }
    )
    endpoint_port = _as_int(ctx.get("endpoint_port"))
    if endpoint_port and not _as_int(target.get("port")):
        target["port"] = endpoint_port

    auth["mode"] = str(auth.get("mode") or "ntlm")
    auth["username"] = username
    auth["secret_ref"] = secret_ref
    if domain_name:
        auth["domain"] = domain_name

    if not isinstance(options.get("timeout_sec"), int):
        options["timeout_sec"] = int(options.get("timeout_sec") or 20)

    context["storage_root_id"] = int(storage_root_id)
    if access_profile_id:
        context["access_profile_id"] = int(access_profile_id)
    elif profile_row and _as_int(profile_row.get("access_profile_id")):
        context["access_profile_id"] = int(_as_int(profile_row.get("access_profile_id")) or 0)
    if resolved_level:
        context["access_level_code"] = resolved_level

    return target, auth, options, context


async def _enrich_storage_root_probe_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    target = dict(payload.get("target") or {})
    auth = dict(payload.get("auth") or {})
    options = dict(payload.get("options") or {})
    context = dict(payload.get("context") or {})

    storage_root_id = _as_int(target.get("storage_root_id")) or _as_int(context.get("storage_root_id"))
    if not storage_root_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "PROBE_STORAGE_ROOT_CONTEXT_REQUIRED",
                "message": "Storage root probe requires target.storage_root_id",
                "missing_fields": ["target.storage_root_id"],
            },
        )

    ctx = await dal_get(f"/api/internal/provisioning/storage-roots/{int(storage_root_id)}/context", timeout=5)
    if not isinstance(ctx, dict):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "PROBE_STORAGE_ROOT_CONTEXT_NOT_FOUND",
                "message": "Storage root provisioning context not found",
                "storage_root_id": int(storage_root_id),
            },
        )

    parsed_host, parsed_share, parsed_rel = _parse_unc_root_path(ctx.get("root_path"))
    host = str(target.get("host") or parsed_host or ctx.get("host") or "").strip()
    share = str(target.get("share") or parsed_share or "").strip()
    rel_path = str(target.get("path") or parsed_rel or "").strip().strip("/\\")
    username = str(
        auth.get("username")
        or auth.get("bind_dn")
        or ctx.get("endpoint_bind_dn")
        or ctx.get("identity_source_bind_dn")
        or ""
    ).strip()
    secret_ref = str(
        auth.get("secret_ref")
        or ctx.get("endpoint_bind_password_ref")
        or ctx.get("identity_source_bind_password_ref")
        or ctx.get("secret_ref")
        or ""
    ).strip()

    missing_fields: list[str] = []
    if not host:
        missing_fields.append("host")
    if not share:
        missing_fields.append("share")
    if not username:
        missing_fields.append("username")
    if not secret_ref:
        missing_fields.append("secret_ref")
    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "PROBE_STORAGE_ROOT_INPUT_MISSING",
                "message": "Unable to build storage root probe payload from context",
                "storage_root_id": int(storage_root_id),
                "missing_fields": missing_fields,
            },
        )

    target.update(
        {
            "host": host,
            "share": share,
            "path": rel_path,
            "storage_root_id": int(storage_root_id),
        }
    )
    endpoint_id = _as_int(ctx.get("storage_endpoint_id"))
    if endpoint_id:
        target["storage_endpoint_id"] = int(endpoint_id)
        context["storage_endpoint_id"] = int(endpoint_id)
    endpoint_port = _as_int(ctx.get("endpoint_port"))
    if endpoint_port and not _as_int(target.get("port")):
        target["port"] = endpoint_port

    auth["mode"] = str(auth.get("mode") or "ntlm")
    auth["username"] = username
    auth["secret_ref"] = secret_ref
    domain_name = str(auth.get("domain") or ctx.get("domain_name") or "").strip()
    if domain_name:
        auth["domain"] = domain_name

    if not isinstance(options.get("timeout_sec"), int):
        options["timeout_sec"] = int(options.get("timeout_sec") or 20)
    options["discover_permissions"] = bool(options.get("discover_permissions", True))
    options["discover_content_size"] = bool(options.get("discover_content_size", True))

    context["storage_root_id"] = int(storage_root_id)
    context["storage_root_name"] = str(ctx.get("storage_root_name") or context.get("storage_root_name") or "").strip() or None
    return target, auth, options, context


def _pick_template(kind: str, protocol: str) -> tuple[str, str]:
    kind_norm = (kind or "").strip().lower()
    protocol_norm = (protocol or "").strip().lower()

    if kind_norm == "identity-search" and protocol_norm == "ldap":
        return "search_ldap_principals", "v1"
    if kind_norm == "identity-search" and protocol_norm == "ldaps":
        return "search_ldaps_principals", "v1"
    if kind_norm == "identity-source" and protocol_norm == "ldap":
        return "test_ldap", "v1"
    if kind_norm == "identity-source" and protocol_norm == "ldaps":
        return "test_ldaps", "v1"
    if kind_norm == "storage-endpoint" and protocol_norm == "smb":
        return "test_smb_ntlm", "v1"
    if kind_norm == "storage-root" and protocol_norm == "smb":
        return "test_smb_root_access", "v1"
    if kind_norm == "acl" and protocol_norm == "acl_push":
        return "acl_apply_via_group", "v1"

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported probe kind/protocol: {kind_norm}/{protocol_norm}",
    )


def _job_type_for_template(template_slug: str) -> str:
    slug = str(template_slug or "").strip().lower()
    try:
        return _PROBE_JOB_TYPE_BY_TEMPLATE[slug]
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "PROBE_TEMPLATE_UNSUPPORTED",
                "message": "Probe template has no job contract mapping",
                "template": slug or None,
            },
        ) from exc


async def submit_probe_run(payload: dict[str, Any]) -> dict[str, Any]:
    template_slug, template_version = _pick_template(
        str(payload.get("kind") or ""),
        str(payload.get("protocol") or ""),
    )
    correlation_id = f"prb_{uuid.uuid4().hex}"
    job_type = _job_type_for_template(template_slug)

    target = dict(payload.get("target") or {})
    auth = dict(payload.get("auth") or {})
    options = dict(payload.get("options") or {})
    context = dict(payload.get("context") or {})

    if template_slug == "acl_apply_via_group":
        target, auth, options, context = await _enrich_acl_probe_payload(payload)
    if template_slug == "test_smb_root_access":
        target, auth, options, context = await _enrich_storage_root_probe_payload(payload)

    identity_source_id = _as_int(context.get("identity_source_id"))
    timeout_sec = int(options.get("timeout_sec") or 30)
    active_job = await _find_equivalent_active_probe(
        template_slug=template_slug,
        job_type=job_type,
        target=target,
        context=context,
    )
    if active_job:
        max_age_seconds = max(90, timeout_sec * 3)
        age_seconds = _job_age_seconds(active_job)
        active_job_id = int(active_job.get("id") or 0)
        if age_seconds <= max_age_seconds and active_job_id > 0:
            return {
                "job_id": str(active_job_id),
                "status": str(active_job.get("status") or "queued").strip().lower(),
                "poll_url": f"/api/probes/jobs/{active_job_id}",
                "reused": True,
            }
        await _fail_stale_probe_job(
            active_job,
            template_slug=template_slug,
            max_age_seconds=max_age_seconds,
        )

    create_job = await dal_post(
        "/api/internal/provisioning/jobs",
        {
            "correlation_id": correlation_id,
            "job_type": job_type,
            "action": template_slug,
            "status": "QUEUED",
            "identity_source_id": identity_source_id,
            "payload_json": {
                "action": template_slug,
                "payload": {
                    "template": {"slug": template_slug, "version": template_version},
                    "kind": payload.get("kind"),
                    "protocol": payload.get("protocol"),
                    "scope": payload.get("scope"),
                    "target": target,
                    "auth": auth,
                    "options": options,
                    "context": context,
                },
            },
        },
    )
    job = (create_job or {}).get("data") or {}
    job_id = int(job.get("id") or 0)
    if job_id <= 0:
        raise HTTPException(status_code=500, detail="Failed to create probe job")

    logger.info(
        "probes.submit",
        extra={
            "job_id": job_id,
            "template": f"{template_slug}:{template_version}",
            "kind": payload.get("kind"),
            "protocol": payload.get("protocol"),
        },
    )

    publish_job(job_type, job_id)

    return {
        "job_id": str(job_id),
        "status": "queued",
        "poll_url": f"/api/probes/jobs/{job_id}",
    }


async def fetch_probe_job(job_id: int | str) -> dict[str, Any]:
    numeric_job_id = int(job_id)
    row = await dal_get(f"/api/internal/provisioning/jobs/{numeric_job_id}")
    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail="Probe job not found")

    status_raw = str(row.get("status") or "").strip().lower()
    if status_raw in {"queued", "running", "retrying"}:
        timeout_sec = _probe_timeout_seconds(row)
        max_age_seconds = max(90, timeout_sec * 3)
        if _job_age_seconds(row) > max_age_seconds:
            await _fail_stale_probe_job(
                row,
                template_slug=str(row.get("action") or "probe").strip() or "probe",
                max_age_seconds=max_age_seconds,
            )
            refreshed = await dal_get(f"/api/internal/provisioning/jobs/{numeric_job_id}")
            if isinstance(refreshed, dict):
                row = refreshed

    data = build_job_run_data(numeric_job_id, row)
    status_value = str(data.get("status") or "queued")
    progress_step = "queued" if status_value in {"queued", "retrying"} else "executing" if status_value == "running" else "done"
    data["progress"] = {"step": progress_step}
    return data
