from __future__ import annotations

import ssl
from typing import Any, Dict
from uuid import UUID

from ldap3 import ALL, Connection, Server, Tls


def _escape_dn_value(value: str) -> str:
    raw = str(value or "")
    out = raw.replace("\\", "\\\\").replace(",", "\\,").replace("+", "\\+")
    out = out.replace('"', '\\"').replace(";", "\\;").replace("<", "\\<").replace(">", "\\>")
    if out.startswith(" ") or out.startswith("#"):
        out = "\\" + out
    if out.endswith(" "):
        out = out[:-1] + "\\ "
    return out


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _guid_to_str(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)) and len(raw) == 16:
        try:
            return str(UUID(bytes_le=bytes(raw)))
        except Exception:
            return None
    text = str(raw).strip()
    return text or None


def ensure_ad_group(params: Dict[str, Any]):
    """Ensure AD group exists (idempotent)."""

    group_name = str(params.get("group_name") or "").strip()
    if not group_name:
        return False, "Missing required field: group_name", {"field": "group_name"}

    identity_source = params.get("identity_source") if isinstance(params.get("identity_source"), dict) else {}

    target_ou_dn = str(params.get("target_ou_dn") or "").strip()
    host = str(params.get("host") or identity_source.get("host") or "").strip()
    bind_dn = str(params.get("bind_dn") or identity_source.get("bind_dn") or params.get("username") or "").strip()
    password = str(params.get("password") or "")
    protocol = str(params.get("protocol") or identity_source.get("protocol") or "ldaps").strip().lower()
    use_ssl = protocol == "ldaps" or int(params.get("port") or identity_source.get("port") or 0) == 636
    verify_tls = _as_bool(params.get("verify_tls"), default=False)
    port = int(params.get("port") or identity_source.get("port") or (636 if use_ssl else 389))
    timeout = int(params.get("timeout") or params.get("timeout_sec") or 5)
    timeout = max(1, min(timeout, 5))

    if not host:
        return False, "Missing required field: identity_source.host", {"field": "identity_source.host"}
    if not bind_dn:
        return False, "Missing required field: identity_source.bind_dn", {"field": "identity_source.bind_dn"}
    if not password:
        return False, "Missing required field: password", {"field": "password"}
    if not target_ou_dn:
        return False, "Missing required field: target_ou_dn", {"field": "target_ou_dn"}

    escaped_cn = _escape_dn_value(group_name)
    group_dn = f"CN={escaped_cn},{target_ou_dn}"

    tls = None
    if use_ssl:
        tls = Tls(validate=ssl.CERT_REQUIRED if verify_tls else ssl.CERT_NONE)

    conn = None
    try:
        server = Server(host, port=port, use_ssl=use_ssl, get_info=ALL, connect_timeout=timeout, tls=tls)
        conn = Connection(server, user=bind_dn, password=password, auto_bind=True, receive_timeout=timeout)

        # Validate target OU exists and is reachable before group operations.
        conn.search(
            search_base=target_ou_dn,
            search_filter="(objectClass=organizationalUnit)",
            attributes=["distinguishedName"],
            size_limit=1,
        )
        if not conn.entries:
            return False, "Target OU not found", {"target_ou_dn": target_ou_dn, "field": "target_ou_dn"}

        search_filter = f"(&(objectClass=group)(cn={group_name}))"
        conn.search(
            search_base=target_ou_dn,
            search_filter=search_filter,
            attributes=["distinguishedName", "cn", "objectGUID"],
            size_limit=1,
        )

        if conn.entries:
            existing_dn = str(getattr(conn.entries[0], "entry_dn", "") or group_dn)
            details = {
                "group_name": group_name,
                "group_dn": existing_dn,
                "group_external_id": existing_dn,
                "group_guid": _guid_to_str(getattr(conn.entries[0], "objectGUID", None)),
                "target_ou_dn": target_ou_dn,
                "directory_server_hint": host,
                "description_text": str(params.get("description_text") or "").strip() or None,
                "operation": "ensure_ad_group",
                "ensured": True,
                "created": False,
                "idempotent": True,
            }
            return True, "AD group already exists", details

        attributes = {
            "sAMAccountName": group_name,
            "groupType": -2147483646,  # GLOBAL + SECURITY
        }
        description_text = str(params.get("description_text") or "").strip()
        if description_text:
            attributes["description"] = description_text

        created = conn.add(group_dn, ["top", "group"], attributes)
        if not created:
            result = dict(getattr(conn, "result", {}) or {})
            result_desc = str(result.get("description") or "").lower()
            if "exists" in result_desc:
                details = {
                    "group_name": group_name,
                    "group_dn": group_dn,
                    "group_external_id": group_dn,
                    "target_ou_dn": target_ou_dn,
                    "directory_server_hint": host,
                    "description_text": description_text or None,
                    "operation": "ensure_ad_group",
                    "ensured": True,
                    "created": False,
                    "idempotent": True,
                }
                return True, "AD group already exists", details
            return False, "LDAP add group failed", {"group_dn": group_dn, "error": str(result)[:2000]}

        details = {
            "group_name": group_name,
            "group_dn": group_dn,
            "group_external_id": group_dn,
            "group_guid": None,
            "target_ou_dn": target_ou_dn,
            "directory_server_hint": host,
            "description_text": description_text or None,
            "operation": "ensure_ad_group",
            "ensured": True,
            "created": True,
            "idempotent": True,
        }

        # Read back created object to capture objectGUID when available.
        try:
            conn.search(
                search_base=target_ou_dn,
                search_filter=search_filter,
                attributes=["distinguishedName", "objectGUID"],
                size_limit=1,
            )
            if conn.entries:
                details["group_dn"] = str(getattr(conn.entries[0], "entry_dn", "") or details["group_dn"])
                details["group_external_id"] = details["group_dn"]
                details["group_guid"] = _guid_to_str(getattr(conn.entries[0], "objectGUID", None))
        except Exception:
            pass

        return True, "AD group created", details
    except Exception as e:
        return False, "LDAP group ensure failed", {"group_name": group_name, "group_dn": group_dn, "error": str(e)[:2000]}
    finally:
        try:
            if conn is not None:
                conn.unbind()
        except Exception:
            pass
