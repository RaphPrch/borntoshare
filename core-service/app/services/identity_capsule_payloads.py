from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.api import identity_sources
from app.core.direct_call import call_route
from app.services.identity_source_accounts import account_for
from app.core.values import positive_int, unwrap_data_dict, unwrap_list


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


def source_tls_fields(source: dict[str, Any]) -> dict[str, Any]:
    """How a worker checks the certificate of this directory."""
    return {
        "directory_flavor": source.get("directory_flavor") or "ad",
        "verify_tls": bool(source.get("tls_verify", True)),
        "tls_ca_pem": source.get("tls_ca_pem") or None,
        "tls_server_name": source.get("tls_server_name") or None,
    }


async def build_identity_source_capsule_context(identity_source_id: int, purpose: str = "snapshot") -> dict[str, Any]:
    """LDAP context of a capsule job; the account is the one of the capability (purpose), else the source's."""
    source = unwrap_data_dict(
        await call_route(identity_sources.get_identity_source_internal, source_id=int(identity_source_id))
    )
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity source not found")

    source_type = str(source.get("type") or "").strip().lower()
    if source_type != "ad":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only AD identity sources are supported",
        )

    if purpose == "provisioning" and not bool((source.get("capabilities") or {}).get("provisioning", source.get("write_enabled"))):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "AD_PROVISIONING_DISABLED",
                "message": "Managing AD groups is disabled for this identity source",
                "identity_source_id": int(identity_source_id),
            },
        )

    protocol = _norm_protocol(source.get("protocol"))
    payload = {
        "identity_source_id": int(identity_source_id),
        "host": str(source.get("host") or "").strip(),
        "bind_dn": str(account_for(source, purpose)[0] or "").strip(),
        "secret_ref": str(account_for(source, purpose)[1] or "").strip(),
        "protocol": protocol,
        "port": _norm_port(source.get("port"), protocol),
        "base_dn": str(source.get("base_dn") or "").strip(),
        **source_tls_fields(source),
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
    rows = unwrap_list(await call_route(identity_sources.list_identity_sources))
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "").strip().lower() != "ad":
            continue
        candidate = positive_int(row.get("id"))
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
