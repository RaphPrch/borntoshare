from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence

from app.actions.acl import apply_acl_via_group
from app.actions.ad_group import ensure_ad_group
from app.actions.ad_group_member import ensure_ad_group_member, remove_ad_group_member
from app.actions.directory_snapshot import collect_directory_snapshot
from app.actions.kerberos import test_kerberos
from app.actions.ldap_group_recursive import discover_group_users_recursive
from app.actions.ldap_search import search_ldap_principals
from app.actions.ldap_test import test_ldap_bind
from app.actions.smb import test_smb_ntlm, test_smb_root_access
from app.middleware.resolve_secrets import CapsuleSecretResolutionError, resolve_secret_fields
from app.schemas.actions import (
    ACLApplyPayload,
    ADGroupCreatePayload,
    ADGroupMemberPayload,
    DirectorySnapshotPayload,
    KerberosAuthPayload,
    LDAPRecursiveGroupUsersPayload,
    LDAPSearchPayload,
    LDAPTestPayload,
    SMBProbePayload,
    SMBRootProbePayload,
)

logger = logging.getLogger("capsule-runner.registry")


@dataclass
class CapsuleActionError(RuntimeError):
    error_code: str
    message: str
    retryable: bool = False
    details: Optional[dict[str, Any]] = None

    def __post_init__(self) -> None:
        super().__init__(self.message)


@dataclass(frozen=True)
class ActionSpec:
    action: str
    schema: Any
    runner: Callable[[dict], tuple[bool, str, dict]]
    secret_fields: Sequence[str]
    target_field: str


ALLOWED_ACTIONS: Dict[str, ActionSpec] = {
    "collect_directory_snapshot": ActionSpec(
        action="collect_directory_snapshot",
        schema=DirectorySnapshotPayload,
        runner=collect_directory_snapshot,
        secret_fields=("secret_ref",),
        target_field="host",
    ),
    "test_smb_ntlm": ActionSpec(
        action="test_smb_ntlm",
        schema=SMBProbePayload,
        runner=test_smb_ntlm,
        secret_fields=("secret_ref",),
        target_field="host",
    ),
    "test_smb_root_access": ActionSpec(
        action="test_smb_root_access",
        schema=SMBRootProbePayload,
        runner=test_smb_root_access,
        secret_fields=("secret_ref",),
        target_field="host",
    ),
    "test_ldap": ActionSpec(
        action="test_ldap",
        schema=LDAPTestPayload,
        runner=test_ldap_bind,
        secret_fields=("secret_ref",),
        target_field="host",
    ),
    "test_ldaps": ActionSpec(
        action="test_ldaps",
        schema=LDAPTestPayload,
        runner=test_ldap_bind,
        secret_fields=("secret_ref",),
        target_field="host",
    ),
    "search_ldap_principals": ActionSpec(
        action="search_ldap_principals",
        schema=LDAPSearchPayload,
        runner=search_ldap_principals,
        secret_fields=("secret_ref",),
        target_field="host",
    ),
    "search_ldaps_principals": ActionSpec(
        action="search_ldaps_principals",
        schema=LDAPSearchPayload,
        runner=search_ldap_principals,
        secret_fields=("secret_ref",),
        target_field="host",
    ),
    "test_kerberos": ActionSpec(
        action="test_kerberos",
        schema=KerberosAuthPayload,
        runner=test_kerberos,
        secret_fields=("secret_ref",),
        target_field="principal",
    ),
    "ensure_ad_group": ActionSpec(
        action="ensure_ad_group",
        schema=ADGroupCreatePayload,
        runner=ensure_ad_group,
        secret_fields=("secret_ref",),
        target_field="group_name",
    ),
    "ensure_ad_group_member": ActionSpec(
        action="ensure_ad_group_member",
        schema=ADGroupMemberPayload,
        runner=ensure_ad_group_member,
        secret_fields=("secret_ref",),
        target_field="group_ref",
    ),
    "remove_ad_group_member": ActionSpec(
        action="remove_ad_group_member",
        schema=ADGroupMemberPayload,
        runner=remove_ad_group_member,
        secret_fields=("secret_ref",),
        target_field="group_ref",
    ),
    "discover_group_users_recursive": ActionSpec(
        action="discover_group_users_recursive",
        schema=LDAPRecursiveGroupUsersPayload,
        runner=discover_group_users_recursive,
        secret_fields=("secret_ref",),
        target_field="root_group_dn",
    ),
    "acl_apply_via_group": ActionSpec(
        action="acl_apply_via_group",
        schema=ACLApplyPayload,
        runner=apply_acl_via_group,
        secret_fields=("secret_ref",),
        target_field="host",
    ),
}


def _flatten_inputs_payload(inputs: dict) -> dict:
    merged = dict(inputs or {})
    if isinstance(inputs.get("target"), dict):
        merged.update(inputs.get("target") or {})
    if isinstance(inputs.get("auth"), dict):
        merged.update(inputs.get("auth") or {})
    if isinstance(inputs.get("options"), dict):
        merged.update(inputs.get("options") or {})
        merged["options"] = inputs.get("options") or {}
    if "timeout_sec" in merged and "timeout" not in merged:
        merged["timeout"] = merged.get("timeout_sec")
    return merged


def _normalize_payload_for_slug(slug: str, payload: dict) -> dict:
    out = dict(payload)
    if slug in {"test_ldaps", "search_ldaps_principals"}:
        out["use_ssl"] = True
    if slug in {"test_ldap", "search_ldap_principals"}:
        out["use_ssl"] = False
    if slug == "ensure_ad_group" and not out.get("target_ou_dn") and out.get("effective_group_ou_dn"):
        out["target_ou_dn"] = out.get("effective_group_ou_dn")
    return out


def _error_code_from_action_failure(action: str, message: str, details: dict[str, Any]) -> str:
    explicit = str(details.get("failure_code") or details.get("error_code") or "").strip().upper()
    if explicit:
        return explicit[:64]

    msg = str(message or "").lower()
    if "timeout" in msg:
        return "CAPSULE_TIMEOUT"
    if "authentication" in msg or "logon failure" in msg or "invalid credentials" in msg:
        return "CAPSULE_AUTH_FAILED"
    if "tls" in msg or "certificate" in msg:
        return "CAPSULE_TLS_FAILED"
    if "dns" in msg or "name or service not known" in msg or "could not resolve" in msg:
        return "CAPSULE_DNS_FAILED"
    if "connection refused" in msg or "port" in msg:
        return "CAPSULE_PORT_UNREACHABLE"
    if "denied" in msg or "permission" in msg:
        return "CAPSULE_PERMISSION_DENIED"
    if action in {"test_ldap", "test_ldaps", "search_ldap_principals", "search_ldaps_principals"}:
        return "CAPSULE_LDAP_FAILED"
    if action == "test_smb_ntlm":
        return "CAPSULE_SMB_FAILED"
    return "CAPSULE_EXECUTION_FAILED"


def execute_action(slug: str, inputs: dict, *, job_id: Optional[int] = None) -> dict:
    spec = ALLOWED_ACTIONS.get(str(slug or "").strip())
    if not spec:
        logger.warning(
            "CAPSULE_ACTION_REJECTED",
            extra={
                "error_code": "CAPSULE_INVALID_ACTION",
                "job_id": job_id,
                "action": slug,
                "status": "rejected",
            },
        )
        raise CapsuleActionError(
            error_code="CAPSULE_INVALID_ACTION",
            message=f"Unsupported action: {slug}",
            retryable=False,
        )

    base_payload = _flatten_inputs_payload(inputs or {})
    normalized = _normalize_payload_for_slug(spec.action, base_payload)
    model_fields = set(getattr(spec.schema, "model_fields", {}).keys())
    normalized = {k: v for k, v in normalized.items() if k in model_fields}

    try:
        model = spec.schema.model_validate(normalized)
    except Exception as exc:
        raise CapsuleActionError(
            error_code="CAPSULE_INVALID_PAYLOAD",
            message=str(exc)[:2000],
            retryable=False,
        ) from exc

    payload = model.model_dump()
    target = payload.get(spec.target_field)
    start = time.monotonic()
    logger.info(
        "CAPSULE_JOB_STARTED",
        extra={
            "job_id": job_id,
            "action": spec.action,
            "target": target,
            "status": "started",
        },
    )

    try:
        payload = resolve_secret_fields(payload, spec.secret_fields)
    except CapsuleSecretResolutionError as exc:
        retryable = exc.error_code in {"SECRET_PROVIDER_FAILURE", "SECRET_PERSISTENCE_FAILURE"}
        logger.warning(
            "CAPSULE_SECRET_RESOLUTION_FAILED",
            extra={
                "job_id": job_id,
                "action": spec.action,
                "target": target,
                "status": "failed",
                "error_code": "CAPSULE_SECRET_RESOLUTION_FAILED",
                "secret_ref": exc.secret_ref,
            },
        )
        raise CapsuleActionError(
            error_code="CAPSULE_SECRET_RESOLUTION_FAILED",
            message=exc.message,
            retryable=retryable,
        ) from exc

    try:
        success, message, details = spec.runner(payload)
    except Exception as exc:
        duration = int((time.monotonic() - start) * 1000)
        logger.exception(
            "CAPSULE_JOB_FAILED",
            extra={
                "job_id": job_id,
                "action": spec.action,
                "target": target,
                "duration_ms": duration,
                "status": "failed",
                "error_code": "CAPSULE_EXECUTION_FAILED",
            },
        )
        raise CapsuleActionError(
            error_code="CAPSULE_EXECUTION_FAILED",
            message=str(exc)[:2000],
            retryable=True,
        ) from exc

    duration = int((time.monotonic() - start) * 1000)
    if not success:
        msg = str(message or "")
        details_payload = details if isinstance(details, dict) else {}
        code = _error_code_from_action_failure(spec.action, msg, details_payload)
        retryable = code == "CAPSULE_TIMEOUT"
        logger.warning(
            "CAPSULE_JOB_FAILED",
            extra={
                "job_id": job_id,
                "action": spec.action,
                "target": target,
                "duration_ms": duration,
                "status": "failed",
                "error_code": code,
            },
        )
        raise CapsuleActionError(
            error_code=code,
            message=msg or code,
            retryable=retryable,
            details=details_payload,
        )

    logger.info(
        "CAPSULE_JOB_COMPLETED",
        extra={
            "job_id": job_id,
            "action": spec.action,
            "target": target,
            "duration_ms": duration,
            "status": "succeeded",
        },
    )

    details_payload = details if isinstance(details, dict) else {}
    return {
        "success": True,
        "message": message,
        "details": details_payload,
    }
