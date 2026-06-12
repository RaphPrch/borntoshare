from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.dal_client import dal_get


def _as_int(value: Any) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _norm_protocol(value: Any) -> str:
    proto = str(value or "").strip().lower()
    return proto if proto in {"ldap", "ldaps"} else "ldaps"


def _norm_port(port: Any, protocol: str) -> int:
    try:
        p = int(port)
        if 1 <= p <= 65535:
            return p
    except (TypeError, ValueError):
        pass
    return 636 if protocol == "ldaps" else 389


def _unwrap_data_envelope(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def _unwrap_list_envelope(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if isinstance(items, list):
        return [row for row in items if isinstance(row, dict)]
    data = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


async def build_identity_source_capsule_context(identity_source_id: int) -> dict[str, Any]:
    source = _unwrap_data_envelope(
        await dal_get(f"/api/identity-sources/{int(identity_source_id)}/internal", timeout=5)
    )
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity source not found")

    source_type = str(source.get("type") or "").strip().lower()
    if source_type != "ad":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only AD identity sources are supported",
        )

    protocol = _norm_protocol(source.get("protocol"))
    payload = {
        "identity_source_id": int(identity_source_id),
        "host": str(source.get("host") or "").strip(),
        "bind_dn": str(source.get("bind_dn") or "").strip(),
        "secret_ref": str(source.get("bind_password_ref") or "").strip(),
        "protocol": protocol,
        "port": _norm_port(source.get("port"), protocol),
        "base_dn": str(source.get("base_dn") or "").strip(),
        "verify_tls": False,
        "timeout": 5,
    }

    missing = [k for k in ("host", "bind_dn", "secret_ref", "base_dn") if not payload.get(k)]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "IDENTITY_SOURCE_CONTEXT_INCOMPLETE",
                "message": "Identity source context is incomplete",
                "identity_source_id": int(identity_source_id),
                "missing_fields": missing,
            },
        )

    return payload


async def infer_identity_source_id_from_group_ref(group_ref: str) -> int:
    rows = _unwrap_list_envelope(await dal_get("/api/identity-sources", timeout=5))
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "").strip().lower() != "ad":
            continue
        candidate = _as_int(row.get("id"))
        if candidate:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error_code": "IDENTITY_SOURCE_NOT_FOUND",
            "message": "No active AD identity source found for group operation",
            "group_ref": str(group_ref or "").strip() or None,
        },
    )
