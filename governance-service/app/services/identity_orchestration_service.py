from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import HTTPException, status

from app.core.dal_client import dal_get, dal_patch, dal_post
from app.core.logging import get_logger
from app.services.job_run_service import build_job_run_data
from app.services.provisioning_jobs import create_and_publish_job


MAX_SNAPSHOT_SEARCH_LIMIT = 200
logger = get_logger("gov-identity-orchestration")
_RESOLVE_REASON_TO_ERROR: dict[str, tuple[str, str]] = {
    "NO_CANDIDATE": (
        "IDENTITY_CANDIDATE_MISSING",
        "Identity candidate is missing (external_id/username/email)",
    ),
    "NOT_FOUND_IN_ACTIVE_SNAPSHOT": (
        "IDENTITY_NOT_FOUND",
        "Identity not found in active imported snapshot",
    ),
}


def _with_query(path: str, params: dict[str, Any] | None) -> str:
    query = {k: v for k, v in (params or {}).items() if v is not None and str(v) != ""}
    if not query:
        return path
    return f"{path}?{urlencode(query, doseq=True)}"


def _normalize_candidate(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_identity_id(value: Any) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _extract_principal_from_import_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    principal = item.get("principal")
    if isinstance(principal, dict):
        return principal
    return item


def _normalize_query_payload(raw: dict[str, Any], source_id: int | None) -> dict[str, Any]:
    payload = dict(raw or {})
    payload.setdefault("query", "")
    payload.setdefault("limit", 50)
    payload.setdefault("principal_type", "all")
    payload.setdefault("search_scope", "subtree")
    try:
        limit = int(payload.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    payload["limit"] = max(1, min(limit, MAX_SNAPSHOT_SEARCH_LIMIT))
    if source_id:
        payload["identity_source_id"] = int(source_id)
    return payload


def _to_resolve_payload(principal: dict[str, Any], identity_source_id: int | None, create_if_missing: bool) -> dict[str, Any]:
    external_id = _normalize_candidate(principal.get("external_id") or principal.get("dn") or principal.get("id"))
    username = _normalize_candidate(principal.get("username") or principal.get("upn"))
    email = _normalize_candidate(principal.get("email"))
    return {
        "external_id": external_id,
        "username": username,
        "email": email,
        "identity_source_id": int(identity_source_id) if identity_source_id else None,
        "create_if_missing": bool(create_if_missing),
    }


def _map_resolve_reason_to_error(reason_code: str | None) -> dict[str, Any]:
    normalized = str(reason_code or "NOT_FOUND_IN_ACTIVE_SNAPSHOT").strip().upper() or "NOT_FOUND_IN_ACTIVE_SNAPSHOT"
    code, message = _RESOLVE_REASON_TO_ERROR.get(
        normalized,
        (
            "IDENTITY_RESOLUTION_FAILED",
            "Identity resolution failed",
        ),
    )
    return {
        "code": code,
        "message": message,
        "reason_code": normalized,
    }


def _unwrap_data_envelope(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


async def _resolve_snapshot_id_for_status(source_id: int | None, status_value: str) -> int | None:
    path = _with_query(
        "/api/internal/directory-snapshots/runs",
        {
            "status": str(status_value or "").strip().upper() or None,
            "limit": 1,
            "identity_source_id": int(source_id) if source_id else None,
        },
    )
    try:
        rows = await dal_get(path, timeout=5)
    except Exception:
        return None
    if not isinstance(rows, list) or not rows:
        return None
    return int((rows[0] or {}).get("id") or 0) or None


async def _resolve_searchable_snapshot(source_id: int | None) -> tuple[int | None, str | None]:
    # Prefer ACTIVE (projection/current state), fallback to SUCCEEDED
    # so directory browsing still works right after a successful sync
    # when activation lag exists.
    active = await _resolve_snapshot_id_for_status(source_id, "ACTIVE")
    if active:
        return active, "ACTIVE"

    succeeded = await _resolve_snapshot_id_for_status(source_id, "SUCCEEDED")
    if succeeded:
        return succeeded, "SUCCEEDED"

    return None, None


async def _resolve_ad_identity_id(
    principal: dict[str, Any],
    *,
    identity_source_id: int | None = None,
    create_if_missing: bool = False,
) -> str | None:
    payload = _to_resolve_payload(
        principal,
        identity_source_id=identity_source_id,
        create_if_missing=create_if_missing,
    )
    external_id = payload.get("external_id")
    username = payload.get("username")
    email = payload.get("email")

    if not external_id and not username and not email:
        return None

    resolved = await dal_post(
        "/api/internal/identities/resolve-ad",
        payload,
        timeout=5,
    )
    if not isinstance(resolved, dict) or not bool(resolved.get("found")):
        return None
    return _normalize_candidate(resolved.get("identity_id"))


async def _resolve_ad_identity_ids_batch(
    principals: list[dict[str, Any]],
    *,
    identity_source_id: int | None,
) -> list[int | None]:
    if not principals:
        return []

    payload_items = [
        _to_resolve_payload(principal, identity_source_id=identity_source_id, create_if_missing=False)
        for principal in principals
    ]
    batch_payload = {
        "identity_source_id": int(identity_source_id) if identity_source_id else None,
        "create_if_missing": False,
        "items": payload_items,
    }

    try:
        batch_result = await dal_post("/api/internal/identities/resolve-ad/batch", batch_payload, timeout=8)
    except Exception as exc:
        logger.debug(
            "identity.search.resolve_batch_failed",
            extra={
                "identity_source_id": int(identity_source_id) if identity_source_id else None,
                "items": len(principals),
                "error": str(exc)[:500],
            },
        )
        return [None for _ in principals]

    resolved_rows = (batch_result or {}).get("items") if isinstance(batch_result, dict) else None
    output: list[int | None] = []
    for index in range(len(principals)):
        row = resolved_rows[index] if isinstance(resolved_rows, list) and index < len(resolved_rows) else {}
        if bool((row or {}).get("found")):
            output.append(_normalize_identity_id((row or {}).get("identity_id")))
        else:
            output.append(None)
    return output


def _search_candidate_hints(principal: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    if payload.get("external_id"):
        if _normalize_candidate(principal.get("external_id")):
            hints.append("external_id")
        elif _normalize_candidate(principal.get("dn")):
            hints.append("dn")
        else:
            hints.append("id")
    if payload.get("username"):
        if _normalize_candidate(principal.get("username")):
            hints.append("username")
        elif _normalize_candidate(principal.get("upn")):
            hints.append("upn")
    if payload.get("email"):
        hints.append("email")
    if not hints:
        hints.append("none")
    return hints


async def run_identity_snapshot(incoming: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    source_id = int(incoming.get("identity_source_id") or 0) or None
    if not source_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="identity_source_id is required",
        )

    source = _unwrap_data_envelope(
        await dal_get(f"/api/identity-sources/{int(source_id)}/internal", timeout=5)
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Identity source not found")

    caps = source.get("capabilities") if isinstance(source.get("capabilities"), dict) else {}
    snapshot_enabled = bool(caps.get("snapshot_enabled", False))
    if not snapshot_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "SNAPSHOT_DISABLED",
                "message": "Snapshot is disabled for this identity source",
                "identity_source_id": int(source_id),
            },
        )

    correlation_id = request_id or f"idsnap_{uuid.uuid4().hex}"
    requested_mode = str(incoming.get("mode") or "auto").strip().lower() or "auto"
    force_full = bool(incoming.get("force_full", True))

    snapshot_run = await dal_post(
        "/api/internal/directory-snapshots/runs",
        {
            "identity_source_id": int(source_id),
            "initiated_by": "governance.identity.snapshots.run",
            "snapshot_source": "governance",
            "correlation_id": correlation_id,
            "mode": requested_mode,
            "force_full": force_full,
            "deferred": True,
        },
        timeout=8,
    )

    snapshot_id = int((snapshot_run or {}).get("snapshot_id") or (snapshot_run or {}).get("id") or 0)
    if snapshot_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error_code": "GOVERNANCE_SNAPSHOT_RUN_CREATE_FAILED", "message": "Snapshot run creation failed"},
        )

    protocol = str(source.get("protocol") or "ldaps").strip().lower()
    port = int(source.get("port") or (636 if protocol == "ldaps" else 389))
    payload = {
        "template": {"slug": "collect_directory_snapshot", "version": "v1"},
        "snapshot_id": snapshot_id,
        "identity_source_id": int(source_id),
        "host": source.get("host"),
        "bind_dn": source.get("bind_dn"),
        "secret_ref": source.get("bind_password_ref"),
        "base_dn": source.get("base_dn"),
        "protocol": protocol,
        "port": port,
        "use_ssl": protocol == "ldaps",
        "verify_tls": bool(incoming.get("verify_tls", False)),
        "timeout": int(incoming.get("timeout") or 15),
        "mode": requested_mode,
        "force_full": force_full,
    }

    created = await create_and_publish_job(
        payload={
            "correlation_id": correlation_id,
            "job_type": "DIRECTORY_SNAPSHOT",
            "action": "collect_directory_snapshot",
            "status": "QUEUED",
            "identity_source_id": int(source_id),
            "payload_json": {
                "action": "collect_directory_snapshot",
                "payload": payload,
            },
            "metrics_json": {
                "snapshot_id": snapshot_id,
                "mode": requested_mode,
                "force_full": force_full,
            },
        },
        dal_post_fn=dal_post,
    )

    return {
        "job_id": int(created.get("job_id") or 0),
        "snapshot_id": snapshot_id,
        "status": "queued",
        "correlation_id": correlation_id,
    }


async def search_identity(incoming: dict[str, Any]) -> dict[str, Any]:
    source_id = int(incoming.get("identity_source_id") or 0) or None
    query_payload = _normalize_query_payload(incoming, source_id)
    base_dn = str(query_payload.get("base_dn") or query_payload.get("dn") or "").strip()
    search_scope = str(query_payload.get("search_scope") or "subtree").strip().lower() or "subtree"
    snapshot_id, snapshot_status = await _resolve_searchable_snapshot(source_id)
    if not snapshot_id:
        return {
            "items": [],
            "users": [],
            "groups": [],
            "ous": [],
            "snapshot_id": None,
            "snapshot_status": None,
        }

    result = await dal_get(
        _with_query(
            f"/api/internal/directory-snapshots/runs/{int(snapshot_id)}/search",
            {
                "q": str(query_payload.get("query") or "").strip(),
                "principal_type": str(query_payload.get("principal_type") or "all").strip().lower(),
                "limit": int(query_payload.get("limit") or 50),
                "dn": base_dn,
                "search_scope": search_scope,
                "enabled_only": bool(query_payload.get("enabled_only", False)),
            },
        ),
        timeout=10,
    )
    rows = (result or {}).get("items") if isinstance(result, dict) else result
    snapshot_rows = rows if isinstance(rows, list) else []
    principals: list[dict[str, Any]] = []
    for row in snapshot_rows:
        if not isinstance(row, dict):
            continue
        principals.append(row)

    resolved_identity_ids = await _resolve_ad_identity_ids_batch(
        principals,
        identity_source_id=source_id,
    )

    items: list[dict[str, Any]] = []
    resolved_count = 0
    unresolved_count = 0
    hint_totals: dict[str, int] = {}
    for index, row in enumerate(principals):
        principal_type = str(row.get("principal_type") or "").strip().lower()
        identity_id = resolved_identity_ids[index] if index < len(resolved_identity_ids) else None
        if identity_id is not None:
            resolved_count += 1
        else:
            unresolved_count += 1

        resolve_payload = _to_resolve_payload(row, identity_source_id=source_id, create_if_missing=False)
        for hint in _search_candidate_hints(row, resolve_payload):
            hint_totals[hint] = int(hint_totals.get(hint, 0)) + 1

        items.append(
            {
                "id": row.get("external_id") or row.get("dn"),
                "identity_id": identity_id,
                "type": principal_type,
                "external_id": row.get("external_id"),
                "dn": row.get("dn"),
                "username": row.get("username"),
                "display_name": row.get("display_name"),
                "email": row.get("email"),
                "enabled": bool(row.get("is_active")) if row.get("is_active") is not None else None,
                "identity_source_id": int(source_id) if source_id else None,
            }
        )

    logger.debug(
        "identity.search.results",
        extra={
            "identity_source_id": int(source_id) if source_id else None,
            "snapshot_id": int(snapshot_id),
            "snapshot_status": snapshot_status,
            "results": len(items),
            "resolved_identity_ids": resolved_count,
            "unresolved_identity_ids": unresolved_count,
            "candidate_hints": hint_totals,
        },
    )

    return {
        "items": items,
        "users": [i for i in items if str(i.get("type") or "") == "user"],
        "groups": [i for i in items if str(i.get("type") or "") == "group"],
        "ous": [i for i in items if str(i.get("type") or "") == "ou"],
        "snapshot_id": int(snapshot_id),
        "snapshot_status": snapshot_status,
    }


async def list_identity_overview(query_params: dict[str, Any]) -> list[dict[str, Any]]:
    path = _with_query("/api/identity", query_params)
    data = await dal_get(path, timeout=10)
    if isinstance(data, dict):
        rows = data.get("items")
    else:
        rows = data

    if not isinstance(rows, list):
        return []

    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        identity_id = _normalize_identity_id(item.get("identity_id"))
        if identity_id is None:
            identity_id = _normalize_identity_id(item.get("id"))
        if identity_id is not None:
            item["identity_id"] = identity_id
        normalized.append(item)
    return normalized


async def update_identity(identity_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    data = await dal_patch(f"/api/identity/{int(identity_id)}", payload, timeout=10)
    if isinstance(data, dict):
        return data
    return {"ok": True}


async def import_identity_ad(incoming: dict[str, Any]) -> dict[str, Any]:
    source_id = int(incoming.get("identity_source_id") or 0) or None
    if not source_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "IDENTITY_SOURCE_ID_REQUIRED",
                "message": "identity_source_id is required for AD import",
                "details": {},
            },
        )

    principal = _extract_principal_from_import_item(incoming)
    resolve_payload = _to_resolve_payload(principal, identity_source_id=source_id, create_if_missing=True)
    identity_id = await _resolve_ad_identity_id(
        principal,
        identity_source_id=source_id,
        create_if_missing=True,
    )

    if not identity_id:
        err = _map_resolve_reason_to_error(
            "NO_CANDIDATE" if not (resolve_payload.get("external_id") or resolve_payload.get("username") or resolve_payload.get("email")) else "NOT_FOUND_IN_ACTIVE_SNAPSHOT"
        )
        return {
            "found": False,
            "identity_id": None,
            "error": err,
        }

    return {
        "found": True,
        "identity_id": identity_id,
        "item": {
            "index": 0,
            "identity_id": identity_id,
            "found": True,
        },
    }


async def import_identity_ad_batch(incoming: dict[str, Any]) -> dict[str, Any]:
    source_id = int(incoming.get("identity_source_id") or 0) or None
    if not source_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "IDENTITY_SOURCE_ID_REQUIRED",
                "message": "identity_source_id is required for AD batch import",
                "details": {},
            },
        )

    raw_items = incoming.get("items") if isinstance(incoming, dict) else None
    items = raw_items if isinstance(raw_items, list) else []
    principals = [_extract_principal_from_import_item(raw) for raw in items]

    batch_payload = {
        "identity_source_id": int(source_id),
        "create_if_missing": True,
        "items": [
            _to_resolve_payload(principal, identity_source_id=source_id, create_if_missing=True)
            for principal in principals
        ],
    }
    batch_result = await dal_post("/api/internal/identities/resolve-ad/batch", batch_payload, timeout=8)
    resolved_rows = (batch_result or {}).get("items") if isinstance(batch_result, dict) else None

    resolved_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index in range(len(principals)):
        row = resolved_rows[index] if isinstance(resolved_rows, list) and index < len(resolved_rows) else {}
        if bool((row or {}).get("found")):
            identity_id = _normalize_candidate((row or {}).get("identity_id"))
            if identity_id:
                resolved_items.append(
                    {
                        "index": index,
                        "identity_id": identity_id,
                        "found": True,
                    }
                )
                continue

        reason_code = str((row or {}).get("reason_code") or "").strip().upper() or None
        if reason_code is None:
            item_payload = batch_payload["items"][index] if index < len(batch_payload["items"]) else {}
            reason_code = "NO_CANDIDATE" if not (item_payload.get("external_id") or item_payload.get("username") or item_payload.get("email")) else "NOT_FOUND_IN_ACTIVE_SNAPSHOT"
        err = _map_resolve_reason_to_error(reason_code)
        errors.append(
            {
                "index": index,
                "code": err["code"],
                "message": err["message"],
                "reason_code": err["reason_code"],
            }
        )

    return {
        "count": len(items),
        "resolved": len(resolved_items),
        "unresolved": len(errors),
        "items": resolved_items,
        "errors": errors,
    }


async def discover_identity(incoming: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    source_id = int(incoming.get("identity_source_id") or 0) or None
    if not source_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="identity_source_id is required",
        )

    source = _unwrap_data_envelope(
        await dal_get(f"/api/identity-sources/{int(source_id)}/internal", timeout=5)
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Identity source not found")

    correlation_id = request_id or f"ids_{source_id}"
    payload = {
        "template": {"slug": "search_ldap_principals", "version": "v1"},
        "query": str(incoming.get("query") or "").strip(),
        "limit": int(incoming.get("limit") or 500),
        "principal_type": str(incoming.get("principal_type") or "all").strip().lower(),
        "identity_source_id": int(source_id),
        "host": source.get("host"),
        "port": source.get("port"),
        "protocol": source.get("protocol"),
        "username": source.get("bind_dn"),
        "secret_ref": source.get("bind_password_ref"),
        "base_dn": source.get("base_dn"),
        "search_scope": str(incoming.get("search_scope") or "subtree").strip().lower(),
    }

    created = await create_and_publish_job(
        payload={
            "correlation_id": correlation_id,
            "job_type": "IDENTITY_DISCOVERY",
            "action": "search_ldap_principals",
            "status": "QUEUED",
            "identity_source_id": int(source_id),
            "payload_json": {
                "action": "search_ldap_principals",
                "payload": payload,
            },
        }
    )

    return {
        "job_id": int(created.get("job_id") or 0),
        "status": "queued",
        "correlation_id": correlation_id,
    }


async def get_identity_job(job_id: int) -> dict[str, Any]:
    row = await dal_get(f"/api/internal/provisioning/jobs/{int(job_id)}", timeout=5)
    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail="Job not found")
    return build_job_run_data(job_id, row)
