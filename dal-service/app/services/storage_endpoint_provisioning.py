from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.storage_endpoint import StorageEndpoint
from app.repositories.storage_endpoints_views_repo import StorageEndpointsViewsRepo
from app.services.naming_policy import (
    DEFAULT_REPLACE_MAP,
    DEFAULT_GLOBAL_POLICY,
    compute_rootcode,
    load_global_policy,
    resolve_effective_policy,
    resolve_group_name_from_effective_policy,
)


def _clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _safe_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _requires_ad_identity_source(*, endpoint_type: str | None, protocol: str | None) -> bool:
    normalized_type = str(endpoint_type or "").strip().lower()
    normalized_protocol = str(protocol or "").strip().lower()
    return normalized_type in {"smb", "cifs"} or normalized_protocol in {"smb", "cifs"}


def _warning(code: str, level: str, message: str) -> dict[str, str]:
    return {
        "code": str(code).strip().upper() or "UNKNOWN",
        "level": str(level).strip().lower() or "warning",
        "message": str(message).strip() or "Unknown provisioning warning",
    }


def compute_configuration_status(
    effective_ou: str | None,
    effective_template: str | None,
) -> tuple[str, str, bool]:
    if effective_template and effective_ou:
        return (
            "ready",
            "Provisioning policy is valid and can be applied.",
            True,
        )

    if effective_template and not effective_ou:
        return (
            "warning",
            "OU is not configured. Group creation may fail if no zone or global fallback exists.",
            False,
        )

    return (
        "incomplete",
        "Naming template is not configured.",
        False,
    )


def build_example_groups(
    *,
    effective_policy: dict[str, Any] | None,
) -> dict[str, str | None] | None:
    policy = dict(DEFAULT_GLOBAL_POLICY)
    policy.update(dict(effective_policy or {}))

    template = _clean_text(policy.get("template"))
    if not template:
        return None

    sample_path = r"\\files\corp\finance_rw"

    replace_map_raw = policy.get("replace_map_json")
    if isinstance(replace_map_raw, dict):
        replace_map = {str(k): str(v) for k, v in replace_map_raw.items()}
    else:
        try:
            parsed = json.loads(str(replace_map_raw or ""))
            replace_map = {str(k): str(v) for k, v in parsed.items()} if isinstance(parsed, dict) else dict(DEFAULT_REPLACE_MAP)
        except Exception:
            replace_map = dict(DEFAULT_REPLACE_MAP)

    rootcode_strategy = str(policy.get("rootcode_strategy") or "BASENAME")
    uppercase_raw = policy.get("normalize_uppercase")
    uppercase = True if uppercase_raw is None else _safe_bool(uppercase_raw)

    root_code = compute_rootcode(
        sample_path,
        strategy=rootcode_strategy,
        replace_map=replace_map,
        uppercase=uppercase,
    )

    read = resolve_group_name_from_effective_policy(
        effective_policy=policy,
        zone_code="",
        storage_root_path=sample_path,
        perm="READ",
    )
    write = resolve_group_name_from_effective_policy(
        effective_policy=policy,
        zone_code="",
        storage_root_path=sample_path,
        perm="WRITE",
    )
    return {
        "based_on_root_code": root_code,
        "read": str(read.get("samAccountName") or "") or None,
        "write": str(write.get("samAccountName") or "") or None,
    }


def normalize_storage_endpoint_provisioning_update(payload: dict[str, Any] | None) -> dict[str, Any]:
    incoming = dict(payload or {})

    policy_mode = _clean_text(incoming.get("policy_mode"))
    endpoint_values = incoming.get("endpoint_values") if isinstance(incoming.get("endpoint_values"), dict) else {}

    if policy_mode not in {"inherit", "override"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "INVALID_POLICY_MODE",
                "message": "policy_mode must be either 'inherit' or 'override'",
            },
        )

    ou_dn = _clean_text(endpoint_values.get("ou_dn") if endpoint_values else None)
    naming_template = _clean_text(endpoint_values.get("naming_template") if endpoint_values else None)

    if policy_mode == "override" and not ou_dn and not naming_template:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "ENDPOINT_OVERRIDE_VALUES_REQUIRED",
                "message": "endpoint override requires at least one override value",
            },
        )

    return {
        "policy_mode": policy_mode,
        "endpoint_override_enabled": policy_mode == "override",
        "endpoint_values": {
            "ou_dn": ou_dn,
            "naming_template": naming_template,
        },
    }


def _resolve_warning_list(
    *,
    requires_ad: bool,
    effective_ou: str | None,
    effective_template: str | None,
    effective_row: dict[str, Any],
    effective_identity_source_id: int | None,
    effective_identity_source_name: str | None,
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []

    if not effective_ou:
        warnings.append(_warning("OU_MISSING", "warning", "No effective OU is configured for this endpoint."))

    if not effective_template:
        warnings.append(_warning("NAMING_TEMPLATE_MISSING", "warning", "No effective naming template is configured for this endpoint."))

    if requires_ad:
        if effective_identity_source_id is None:
            warnings.append(_warning("IDENTITY_SOURCE_MISSING", "warning", "No identity source assigned to this SMB endpoint."))
        elif effective_identity_source_name is None:
            warnings.append(_warning("IDENTITY_SOURCE_MISSING", "warning", "Assigned identity source cannot be resolved."))
        else:
            if not _safe_bool(effective_row.get("effective_identity_source_is_active")):
                warnings.append(_warning("IDENTITY_SOURCE_DISABLED", "warning", "Assigned identity source is disabled."))

            source_kind = str(effective_row.get("effective_identity_source_kind") or "").strip().upper()
            if source_kind not in {"AD", "LDAP", "LDAPS"}:
                warnings.append(_warning("IDENTITY_SOURCE_INVALID_KIND", "warning", "Assigned identity source is not AD/LDAP compatible."))

            bind_dn = _clean_text(effective_row.get("effective_identity_source_bind_dn"))
            if not bind_dn:
                warnings.append(_warning("IDENTITY_SOURCE_BIND_DN_MISSING", "warning", "Identity source bind_dn is missing."))

            bind_password_ref = _clean_text(effective_row.get("effective_identity_source_bind_password_ref"))
            if not bind_password_ref:
                warnings.append(_warning("IDENTITY_SOURCE_BIND_SECRET_MISSING", "warning", "Identity source bind_password_ref is missing."))

            host = _clean_text(effective_row.get("effective_identity_source_host"))
            if not host:
                warnings.append(_warning("IDENTITY_SOURCE_HOST_MISSING", "warning", "Identity source host is missing."))

            base_dn = _clean_text(effective_row.get("effective_identity_source_base_dn"))
            if not base_dn:
                warnings.append(_warning("IDENTITY_SOURCE_BASE_DN_MISSING", "warning", "Identity source base_dn is missing."))

    # dedupe by code+message
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for row in warnings:
        key = (str(row.get("code") or ""), str(row.get("message") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def build_storage_endpoint_provisioning_payload(db: Session, endpoint: StorageEndpoint) -> dict[str, Any]:
    effective_row = StorageEndpointsViewsRepo(db).get_effective_provisioning_policy(int(endpoint.id)) or {}

    zone_id = _safe_int(effective_row.get("zone_id") or getattr(endpoint, "zone_id", None))
    zone_name = _clean_text(effective_row.get("zone_name")) or (f"Zone #{zone_id}" if zone_id else None)

    global_naming_policy = load_global_policy(db)
    scope_effective_naming_policy = resolve_effective_policy(
        db,
        int(zone_id) if zone_id else None,
        storage_endpoint_id=int(endpoint.id),
    )

    endpoint_ou = _clean_text(getattr(endpoint, "sub_ou_dn", None) or effective_row.get("endpoint_sub_ou_dn"))
    endpoint_template = _clean_text(getattr(endpoint, "naming_template", None) or effective_row.get("endpoint_naming_template"))

    inherited_ou = (
        _clean_text(effective_row.get("base_ou_dn"))
        or _clean_text(effective_row.get("static_ou_dn"))
        or _clean_text(effective_row.get("effective_ou_dn"))
    )

    inherited_template = (
        _clean_text((scope_effective_naming_policy or {}).get("template"))
        or _clean_text((global_naming_policy or {}).get("template"))
    )

    policy_mode = "override" if (endpoint_ou or endpoint_template) else "inherit"
    endpoint_override_enabled = policy_mode == "override"

    if policy_mode == "override":
        effective_ou = endpoint_ou or inherited_ou
        effective_template = endpoint_template or inherited_template
    else:
        effective_ou = inherited_ou
        effective_template = inherited_template

    effective_ou_status = "configured" if effective_ou else "missing"
    effective_template_status = "configured" if effective_template else "missing"

    configuration_status, configuration_message, is_ready = compute_configuration_status(
        effective_ou=effective_ou,
        effective_template=effective_template,
    )

    effective_identity_source_id = _safe_int(
        effective_row.get("effective_identity_source_id")
        or getattr(endpoint, "identity_source_id", None)
    )
    effective_identity_source_name = _clean_text(effective_row.get("effective_identity_source_name"))

    requires_ad = _requires_ad_identity_source(
        endpoint_type=_clean_text(effective_row.get("endpoint_type") or getattr(endpoint, "endpoint_type", None)),
        protocol=_clean_text(effective_row.get("protocol") or getattr(endpoint, "protocol", None)),
    )

    warnings = _resolve_warning_list(
        requires_ad=requires_ad,
        effective_ou=effective_ou,
        effective_template=effective_template,
        effective_row=effective_row,
        effective_identity_source_id=effective_identity_source_id,
        effective_identity_source_name=effective_identity_source_name,
    )

    has_zone_source = any(
        [
            _clean_text(effective_row.get("base_ou_dn")),
            _clean_text(effective_row.get("static_ou_dn")),
            _clean_text((scope_effective_naming_policy or {}).get("template")),
        ]
    )

    policy_source = "endpoint" if endpoint_override_enabled else ("zone" if has_zone_source else "global")
    policy_source_label = {
        "endpoint": "Storage endpoint override",
        "zone": f"Zone policy ({zone_name})" if zone_name else "Zone policy",
        "global": "Global policy",
    }[policy_source]

    effective_naming_policy = dict(DEFAULT_GLOBAL_POLICY)
    effective_naming_policy.update(dict(global_naming_policy or {}))
    effective_naming_policy.update(dict(scope_effective_naming_policy or {}))
    if effective_template:
        effective_naming_policy["template"] = effective_template

    example_groups = build_example_groups(effective_policy=effective_naming_policy)

    return {
        "storage_endpoint_id": int(endpoint.id),
        "storage_endpoint_name": _clean_text(getattr(endpoint, "name", None)),
        "zone_id": zone_id,
        "zone_name": zone_name,
        "endpoint_type": _clean_text(effective_row.get("endpoint_type") or getattr(endpoint, "endpoint_type", None)),
        "host": _clean_text(getattr(endpoint, "host", None) or effective_row.get("host")),

        # Enriched V1+ payload
        "policy_mode": policy_mode,
        "endpoint_override_enabled": endpoint_override_enabled,
        "policy_source": policy_source,
        "policy_source_label": policy_source_label,
        "endpoint_values": {
            "ou_dn": endpoint_ou,
            "naming_template": endpoint_template,
        },
        "inherited_values": {
            "ou_dn": inherited_ou,
            "naming_template": inherited_template,
        },
        "effective_values": {
            "ou_dn": effective_ou,
            "naming_template": effective_template,
        },
        "effective_ou_status": effective_ou_status,
        "effective_template_status": effective_template_status,
        "configuration_status": configuration_status,
        "configuration_message": configuration_message,
        "is_ready_to_provision": is_ready,
        "warnings": warnings,
        "example_groups": example_groups,
        "effective_naming_policy": {
            "group_prefix": _clean_text(effective_naming_policy.get("group_prefix")) or "B2S",
            "template": _clean_text(effective_naming_policy.get("template")) or "{PREFIX}_{ROOTCODE}_{PERM}",
            "normalize_uppercase": (
                _safe_bool(effective_naming_policy.get("normalize_uppercase"))
                if effective_naming_policy.get("normalize_uppercase") is not None
                else True
            ),
            "max_sam_length": _safe_int(effective_naming_policy.get("max_sam_length")) or 64,
            "rootcode_strategy": _clean_text(effective_naming_policy.get("rootcode_strategy")) or "BASENAME",
        },
        "effective_identity_source": {
            "id": effective_identity_source_id,
            "name": effective_identity_source_name,
        },
    }
