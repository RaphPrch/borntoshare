from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import HTTPException, status


@dataclass(frozen=True)
class ProvisioningContext:
    storage_root_id: Optional[int]
    zone_id: Optional[int]
    identity_source_id: Optional[int]
    effective_secret_ref: Optional[str]
    effective_group_ou_dn: Optional[str]
    domain_name: Optional[str]
    resolved_host: Optional[str]
    resolved_port: Optional[int]
    resolved_protocol: Optional[str]
    resolved_bind_dn: Optional[str]
    write_enabled: bool


def _pick_secret_ref(ctx: Dict[str, Any]) -> Optional[str]:
    candidates = [
        str(ctx.get("secret_ref") or "").strip(),
        str(ctx.get("identity_source_bind_password_ref") or "").strip(),
        str(ctx.get("endpoint_bind_password_ref") or "").strip(),
    ]
    for ref in candidates:
        if ref:
            return ref
    return None


def _pick_group_ou(ctx: Dict[str, Any]) -> Optional[str]:
    candidates = [
        str(ctx.get("effective_group_ou_dn") or "").strip(),
        str(ctx.get("zone_default_group_ou_dn") or "").strip(),
        str(ctx.get("default_group_ou_dn") or "").strip(),
    ]
    for ou in candidates:
        if ou:
            return ou
    return None


def build_provisioning_context(ctx: Dict[str, Any]) -> ProvisioningContext:
    if not isinstance(ctx, dict):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "GOVERNANCE_INVALID_CONTEXT", "message": "Storage root context not found"},
        )

    return ProvisioningContext(
        storage_root_id=int(ctx.get("storage_root_id") or 0) or None,
        zone_id=int(ctx.get("zone_id") or 0) or None,
        identity_source_id=int(ctx.get("identity_source_id") or 0) or None,
        effective_secret_ref=_pick_secret_ref(ctx),
        effective_group_ou_dn=_pick_group_ou(ctx),
        domain_name=str(ctx.get("domain_name") or "").strip() or None,
        resolved_host=str(ctx.get("identity_source_host") or ctx.get("host") or "").strip() or None,
        resolved_port=int(ctx.get("identity_source_port") or ctx.get("endpoint_port") or 0) or None,
        resolved_protocol=str(ctx.get("identity_source_protocol") or ctx.get("endpoint_protocol") or "").strip() or None,
        resolved_bind_dn=str(ctx.get("identity_source_bind_dn") or ctx.get("endpoint_bind_dn") or "").strip() or None,
        write_enabled=bool(ctx.get("write_enabled")),
    )
