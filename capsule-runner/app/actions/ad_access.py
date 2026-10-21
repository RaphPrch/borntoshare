"""Grant access through an AD group: find or create the group, then add the principal.

Everything runs on one LDAP connection, hence on one domain controller: the group
created in step 1 is visible to step 2 without waiting for AD replication.

Group resolution order:
  1. adopt_group_dn: an existing group chosen by an administrator (outcome "adopted")
  2. group_external_id (objectGUID or DN stored by BornToShare): outcome "reused"
  3. sAMAccountName anywhere in the domain:
       - inside the managed OU (target_ou_dn): outcome "reused"
       - elsewhere: AD_GROUP_NAME_CONFLICT (never takes over a group BornToShare did not create)
  4. otherwise: created in target_ou_dn as a global security group (outcome "created",
     or "recreated" when the known group was deleted from AD)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from ldap3 import BASE, MODIFY_ADD, SUBTREE
from ldap3.core import exceptions as ldap_exceptions

from app.actions.ad_group import _escape_dn_value, _guid_to_str
from app.actions.ad_group_member import _entry_get, _escape_filter, _resolve_principal_dn
from app.shared import ldap_client

GLOBAL_SECURITY_GROUP = -2147483646
MANAGED_MARKER = "Managed by BornToShare"
# CN (and so the group name) is limited to 64 characters in AD
MAX_GROUP_NAME = 64
_FORBIDDEN_NAME_CHARS = re.compile(r'["/\\\[\]:;|=,+*?<>@]')
_DN_SPLIT = re.compile(r"(?<!\\),")

# Network errors are worth a retry; everything else is a configuration or data issue
_RETRYABLE_ERRORS = (
    ldap_exceptions.LDAPSocketOpenError,
    ldap_exceptions.LDAPSocketReceiveError,
    ldap_exceptions.LDAPSocketSendError,
    ldap_exceptions.LDAPSessionTerminatedByServerError,
    ldap_exceptions.LDAPResponseTimeoutError,
)


class _Failure(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_dn(value: str) -> str:
    parts = [part.strip() for part in _DN_SPLIT.split(str(value or "")) if part.strip()]
    return ",".join(re.sub(r"\s*=\s*", "=", part).lower() for part in parts)


def _parent_dn(dn: str) -> str:
    parts = _DN_SPLIT.split(str(dn or ""), maxsplit=1)
    return _normalize_dn(parts[1]) if len(parts) == 2 else ""


def _guid_filter(value: str) -> str | None:
    try:
        raw = UUID(str(value).strip()).bytes_le
    except (ValueError, AttributeError):
        return None
    return "(objectGUID=" + "".join(f"\\{byte:02x}" for byte in raw) + ")"


def _find_group(conn: Any, *, base_dn: str, search_filter: str, scope: Any = SUBTREE) -> dict[str, Any] | None:
    conn.search(
        search_base=base_dn,
        search_filter=f"(&(objectClass=group){search_filter})",
        search_scope=scope,
        attributes=["distinguishedName", "sAMAccountName", "objectGUID"],
        size_limit=2,
    )
    if not conn.entries:
        return None
    entry = conn.entries[0]
    return {
        "dn": str(_entry_get(entry, "distinguishedName") or getattr(entry, "entry_dn", "") or "").strip(),
        "sam": str(_entry_get(entry, "sAMAccountName") or "").strip(),
        # ldap3 may format the GUID as "{...}": keep the plain form
        "guid": (_guid_to_str(_entry_get(entry, "objectGUID")) or "").strip("{}") or None,
    }


def _find_known_group(conn: Any, *, base_dn: str, external_id: str) -> dict[str, Any] | None:
    guid_filter = _guid_filter(external_id)
    if guid_filter:
        return _find_group(conn, base_dn=base_dn, search_filter=guid_filter)
    if "=" in external_id:
        try:
            return _find_group(conn, base_dn=external_id, search_filter="", scope=BASE)
        except ldap_exceptions.LDAPNoSuchObjectResult:
            return None
    return None


def _create_group(conn: Any, *, group_name: str, target_ou_dn: str, description: str) -> dict[str, Any]:
    conn.search(
        search_base=target_ou_dn,
        search_filter="(|(objectClass=organizationalUnit)(objectClass=container))",
        search_scope=BASE,
        attributes=["distinguishedName"],
        size_limit=1,
    )
    if not conn.entries:
        raise _Failure(
            "AD_TARGET_OU_NOT_FOUND",
            "The organizational unit of the zone does not exist in Active Directory",
            target_ou_dn=target_ou_dn,
        )
    group_dn = f"CN={_escape_dn_value(group_name)},{target_ou_dn}"
    attributes = {
        "sAMAccountName": group_name,
        "groupType": GLOBAL_SECURITY_GROUP,
        "description": description[:1024] if description else MANAGED_MARKER,
        "info": MANAGED_MARKER,
    }
    if not conn.add(group_dn, ["top", "group"], attributes):
        result = dict(getattr(conn, "result", {}) or {})
        description_text = str(result.get("description") or "").lower()
        if "exists" in description_text:
            # Same CN in the OU with another sAMAccountName: a human must decide
            raise _Failure(
                "AD_GROUP_NAME_CONFLICT",
                "An object with this name already exists in the organizational unit",
                existing_dn=group_dn,
                group_name=group_name,
            )
        if "insufficient" in description_text or "access" in description_text:
            raise _Failure(
                "AD_GROUP_CREATE_DENIED",
                "The service account is not allowed to create groups in this organizational unit",
                target_ou_dn=target_ou_dn,
                ldap_result=str(result)[:500],
            )
        raise _Failure("AD_GROUP_CREATE_FAILED", "Active Directory refused the group creation", ldap_result=str(result)[:500])
    created = _find_group(conn, base_dn=group_dn, search_filter="", scope=BASE) or {}
    return {"dn": created.get("dn") or group_dn, "sam": group_name, "guid": created.get("guid")}


def _ensure_member(conn: Any, *, group_dn: str, principal_dn: str) -> str:
    conn.search(
        search_base=group_dn,
        search_filter="(objectClass=group)",
        search_scope=BASE,
        attributes=["member"],
        size_limit=1,
    )
    members = (getattr(conn.entries[0], "entry_attributes_as_dict", {}) or {}).get("member") or [] if conn.entries else []
    if principal_dn.lower() in {str(value).strip().lower() for value in members}:
        return "already_member"
    if conn.modify(group_dn, {"member": [(MODIFY_ADD, [principal_dn])]}):
        return "added"
    result = dict(getattr(conn, "result", {}) or {})
    text = f"{result.get('description') or ''} {result.get('message') or ''}".lower()
    if "typeorvalueexists" in text or "already" in text:
        return "already_member"
    if "insufficient" in text or "access" in text:
        raise _Failure(
            "AD_MEMBER_WRITE_DENIED",
            "The service account is not allowed to change the members of this group",
            group_dn=group_dn,
            ldap_result=str(result)[:500],
        )
    raise _Failure("AD_MEMBER_ADD_FAILED", "Active Directory refused the membership change", ldap_result=str(result)[:500])


def grant_ad_access(params: dict[str, Any]):
    host = str(params.get("host") or "").strip()
    bind_dn = str(params.get("bind_dn") or "").strip()
    password = str(params.get("password") or "")
    protocol = "ldap" if str(params.get("protocol") or "").strip().lower() == "ldap" else "ldaps"
    port = int(params.get("port") or (636 if protocol == "ldaps" else 389))
    timeout = max(1, min(int(params.get("timeout") or 15), 30))
    base_dn = str(params.get("base_dn") or "").strip()
    target_ou_dn = str(params.get("target_ou_dn") or "").strip()
    group_name = str(params.get("group_name") or "").strip()
    external_id = str(params.get("group_external_id") or "").strip()
    adopt_dn = str(params.get("adopt_group_dn") or "").strip()
    description = str(params.get("description_text") or "").strip()
    principal_dn = str(params.get("principal_dn") or "").strip() or None
    principal_username = str(params.get("principal_username") or "").strip() or None

    steps: list[dict[str, Any]] = []

    def step(name: str, status: str, message: str, **extra: Any) -> None:
        steps.append({"step": name, "status": status, "message": message, "at": _now(), **extra})

    def failure(code: str, message: str, *, retryable: bool = False, **details: Any):
        step("failed", "failed", message, code=code)
        return False, message, {
            "failure_code": code,
            "retryable": retryable,
            "group_name": group_name,
            "target_ou_dn": target_ou_dn,
            "directory_server": host,
            "steps": steps,
            **details,
        }

    missing = [name for name, value in (
        ("host", host), ("bind_dn", bind_dn), ("password", password), ("base_dn", base_dn),
        ("target_ou_dn", target_ou_dn), ("group_name", group_name),
    ) if not value]
    if not principal_dn and not principal_username:
        missing.append("principal_dn|principal_username")
    if missing:
        return failure("AD_ACCESS_PAYLOAD_INCOMPLETE", f"Missing required fields: {', '.join(missing)}", fields=missing)
    if len(group_name) > MAX_GROUP_NAME or _FORBIDDEN_NAME_CHARS.search(group_name):
        return failure(
            "AD_GROUP_NAME_INVALID",
            f"Group name must have at most {MAX_GROUP_NAME} characters and no \" / \\ [ ] : ; | = , + * ? < > @",
        )

    conn = None
    try:
        conn = ldap_client.connect(
            host=host,
            port=port,
            use_ssl=protocol == "ldaps",
            verify_tls=bool(params.get("verify_tls")),
            timeout=timeout,
        )
        if not ldap_client.bind(conn, bind_dn=bind_dn, password=password):
            return failure("AD_BIND_FAILED", "The service account could not sign in to Active Directory", bind_dn=bind_dn)
        step("connect", "done", f"Connected to {host}")

        # 1. Group
        group: dict[str, Any] | None = None
        outcome = ""
        if adopt_dn:
            group = _find_known_group(conn, base_dn=base_dn, external_id=adopt_dn)
            if not group:
                raise _Failure("AD_ADOPT_TARGET_NOT_FOUND", "The group to adopt no longer exists", adopt_group_dn=adopt_dn)
            outcome = "adopted"
        elif external_id:
            group = _find_known_group(conn, base_dn=base_dn, external_id=external_id)
            outcome = "reused" if group else ""
            if not group:
                step("group", "warning", "The known group no longer exists in Active Directory", group_external_id=external_id)
        if not group:
            existing = _find_group(conn, base_dn=base_dn, search_filter=f"(sAMAccountName={_escape_filter(group_name)})")
            if existing and _parent_dn(existing["dn"]) == _normalize_dn(target_ou_dn):
                group, outcome = existing, "reused"
            elif existing:
                raise _Failure(
                    "AD_GROUP_NAME_CONFLICT",
                    "A group with this name already exists outside the organizational unit of the zone",
                    existing_dn=existing["dn"],
                    group_name=group_name,
                )
            else:
                group = _create_group(conn, group_name=group_name, target_ou_dn=target_ou_dn, description=description)
                outcome = "recreated" if external_id else "created"
        step("group", "done", f"Group {outcome}", outcome=outcome, group_dn=group["dn"])

        # 2. Member
        try:
            resolved_principal = _resolve_principal_dn(
                conn,
                base_dn=base_dn,
                principal_dn=principal_dn,
                principal_username=principal_username,
            )
        except ValueError as exc:
            raise _Failure("AD_PRINCIPAL_NOT_FOUND", "The requester was not found in Active Directory", reason=str(exc)) from exc
        member_outcome = _ensure_member(conn, group_dn=group["dn"], principal_dn=resolved_principal)
        step("member", "done", "Member added" if member_outcome == "added" else "Already a member", outcome=member_outcome)

        return True, "AD access granted", {
            "operation": "grant_ad_access",
            "group_name": group.get("sam") or group_name,
            "group_dn": group["dn"],
            "group_guid": group.get("guid"),
            "group_external_id": group.get("guid") or group["dn"],
            "group_outcome": outcome,
            "member_outcome": member_outcome,
            "principal_dn": resolved_principal,
            "target_ou_dn": target_ou_dn,
            "directory_server": host,
            "steps": steps,
        }
    except _Failure as exc:
        return failure(exc.code, exc.message, retryable=exc.retryable, **exc.details)
    except _RETRYABLE_ERRORS as exc:
        if any(marker in str(exc).lower() for marker in ("certificate", "ssl", "tls")):
            # Certificate refused (CA, host name, expiry): retrying will not fix it
            return failure("AD_TLS_FAILED", "The certificate of the domain controller was refused", error=str(exc)[:500])
        return failure("AD_UNREACHABLE", "Active Directory did not answer", retryable=True, error=str(exc)[:500])
    except ldap_exceptions.LDAPException as exc:
        return failure("AD_LDAP_ERROR", "LDAP error", error=str(exc)[:500])
    finally:
        try:
            if conn is not None:
                conn.unbind()
        except Exception:
            pass
