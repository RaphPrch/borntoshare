from __future__ import annotations

from typing import Any

from ldap3 import BASE, MODIFY_ADD, MODIFY_DELETE, SUBTREE

from app.shared import ldap_client


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _escape_filter(value: str) -> str:
    text = str(value or "")
    return (
        text.replace("\\", "\\5c")
        .replace("*", "\\2a")
        .replace("(", "\\28")
        .replace(")", "\\29")
        .replace("\x00", "")
    )


def _entry_get(entry: Any, key: str) -> Any:
    data = getattr(entry, "entry_attributes_as_dict", {}) or {}
    value = data.get(key)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _resolve_group_dn(conn: Any, *, base_dn: str, group_ref: str) -> str:
    raw = str(group_ref or "").strip()
    if not raw:
        raise ValueError("group_ref is required")

    if "=" in raw and "," in raw:
        conn.search(
            search_base=raw,
            search_filter="(objectClass=group)",
            search_scope=BASE,
            attributes=["distinguishedName"],
            size_limit=1,
        )
        if conn.entries:
            return str(_entry_get(conn.entries[0], "distinguishedName") or getattr(conn.entries[0], "entry_dn", "") or raw).strip()

    escaped = _escape_filter(raw)
    conn.search(
        search_base=str(base_dn or "").strip(),
        search_filter=f"(&(objectClass=group)(|(distinguishedName={escaped})(cn={escaped})(sAMAccountName={escaped})))",
        search_scope=SUBTREE,
        attributes=["distinguishedName"],
        size_limit=1,
    )
    if not conn.entries:
        raise ValueError(f"AD group not found: {raw}")
    return str(_entry_get(conn.entries[0], "distinguishedName") or getattr(conn.entries[0], "entry_dn", "") or "").strip()


def _resolve_principal_dn(
    conn: Any,
    *,
    base_dn: str,
    principal_dn: str | None,
    principal_username: str | None,
) -> str:
    raw_dn = str(principal_dn or "").strip()
    if raw_dn:
        conn.search(
            search_base=raw_dn,
            search_filter="(objectClass=*)",
            search_scope=BASE,
            attributes=["distinguishedName"],
            size_limit=1,
        )
        if conn.entries:
            return str(_entry_get(conn.entries[0], "distinguishedName") or getattr(conn.entries[0], "entry_dn", "") or raw_dn).strip()

    username = str(principal_username or "").strip()
    if not username:
        raise ValueError("principal_dn or principal_username is required")

    escaped = _escape_filter(username)
    conn.search(
        search_base=str(base_dn or "").strip(),
        search_filter=(
            "(&(|(objectClass=user)(objectClass=person))"
            f"(|(sAMAccountName={escaped})(userPrincipalName={escaped})(cn={escaped})))"
        ),
        search_scope=SUBTREE,
        attributes=["distinguishedName"],
        size_limit=1,
    )
    if not conn.entries:
        raise ValueError(f"AD principal not found: {username}")
    return str(_entry_get(conn.entries[0], "distinguishedName") or getattr(conn.entries[0], "entry_dn", "") or "").strip()


def _common(params: dict[str, Any]) -> tuple[str, str, str, str, int, bool, int, str, str, str | None, str | None]:
    host = str(params.get("host") or "").strip()
    bind_dn = str(params.get("bind_dn") or params.get("username") or "").strip()
    password = str(params.get("password") or "")
    protocol = str(params.get("protocol") or "ldaps").strip().lower()
    if protocol not in {"ldap", "ldaps"}:
        protocol = "ldaps"
    use_ssl = protocol == "ldaps" or int(params.get("port") or 0) == 636
    port = int(params.get("port") or (636 if use_ssl else 389))
    timeout = int(params.get("timeout") or params.get("timeout_sec") or 5)
    timeout = max(1, min(timeout, 30))
    verify_tls = _as_bool(params.get("verify_tls"), default=False)
    base_dn = str(params.get("base_dn") or "").strip()
    group_ref = str(params.get("group_ref") or "").strip()
    principal_dn = str(params.get("principal_dn") or "").strip() or None
    principal_username = str(params.get("principal_username") or "").strip() or None
    return (
        host,
        bind_dn,
        password,
        protocol,
        port,
        verify_tls,
        timeout,
        base_dn,
        group_ref,
        principal_dn,
        principal_username,
    )


def ensure_ad_group_member(params: dict[str, Any]):
    (
        host,
        bind_dn,
        password,
        protocol,
        port,
        verify_tls,
        timeout,
        base_dn,
        group_ref,
        principal_dn,
        principal_username,
    ) = _common(params)

    if not host:
        return False, "Missing required field: host", {"field": "host"}
    if not bind_dn:
        return False, "Missing required field: bind_dn", {"field": "bind_dn"}
    if not password:
        return False, "Missing required field: password", {"field": "password"}
    if not base_dn:
        return False, "Missing required field: base_dn", {"field": "base_dn"}
    if not group_ref:
        return False, "Missing required field: group_ref", {"field": "group_ref"}
    if not principal_dn and not principal_username:
        return False, "Missing required field: principal_dn|principal_username", {"field": "principal_dn"}

    conn = None
    try:
        conn = ldap_client.connect(
            host=host,
            port=port,
            use_ssl=(protocol == "ldaps"),
            verify_tls=verify_tls,
            timeout=timeout,
        )
        if not ldap_client.bind(conn, bind_dn=bind_dn, password=password):
            return False, "LDAP bind failed", {"host": host, "port": port}

        resolved_group_dn = _resolve_group_dn(conn, base_dn=base_dn, group_ref=group_ref)
        resolved_principal_dn = _resolve_principal_dn(
            conn,
            base_dn=base_dn,
            principal_dn=principal_dn,
            principal_username=principal_username,
        )

        conn.search(
            search_base=resolved_group_dn,
            search_filter="(objectClass=group)",
            search_scope=BASE,
            attributes=["member"],
            size_limit=1,
        )
        if conn.entries:
            members = getattr(conn.entries[0], "entry_attributes_as_dict", {}).get("member") or []
            member_lc = {str(v).strip().lower() for v in members if str(v).strip()}
            if resolved_principal_dn.lower() in member_lc:
                return True, "AD group membership already present", {
                    "ok": True,
                    "added": False,
                    "reason": "already_member",
                    "group_dn": resolved_group_dn,
                    "principal_dn": resolved_principal_dn,
                    "operation": "ensure_ad_group_member",
                }

        ok = conn.modify(
            resolved_group_dn,
            {"member": [(MODIFY_ADD, [resolved_principal_dn])]},
        )
        if not ok:
            result = dict(getattr(conn, "result", {}) or {})
            desc = str(result.get("description") or "").lower()
            msg = str(result.get("message") or "").lower()
            if "typeorvalueexists" in desc or "already" in msg:
                return True, "AD group membership already present", {
                    "ok": True,
                    "added": False,
                    "reason": "already_member",
                    "group_dn": resolved_group_dn,
                    "principal_dn": resolved_principal_dn,
                    "operation": "ensure_ad_group_member",
                }
            return False, "LDAP group membership ensure failed", {
                "group_dn": resolved_group_dn,
                "principal_dn": resolved_principal_dn,
                "error": str(result)[:2000],
            }

        return True, "AD group membership ensured", {
            "ok": True,
            "added": True,
            "reason": "added",
            "group_dn": resolved_group_dn,
            "principal_dn": resolved_principal_dn,
            "operation": "ensure_ad_group_member",
        }
    except Exception as exc:
        return False, "LDAP group membership ensure failed", {"error": str(exc)[:2000]}
    finally:
        try:
            if conn is not None:
                conn.unbind()
        except Exception:
            pass


def remove_ad_group_member(params: dict[str, Any]):
    (
        host,
        bind_dn,
        password,
        protocol,
        port,
        verify_tls,
        timeout,
        base_dn,
        group_ref,
        principal_dn,
        principal_username,
    ) = _common(params)

    if not host:
        return False, "Missing required field: host", {"field": "host"}
    if not bind_dn:
        return False, "Missing required field: bind_dn", {"field": "bind_dn"}
    if not password:
        return False, "Missing required field: password", {"field": "password"}
    if not base_dn:
        return False, "Missing required field: base_dn", {"field": "base_dn"}
    if not group_ref:
        return False, "Missing required field: group_ref", {"field": "group_ref"}
    if not principal_dn and not principal_username:
        return False, "Missing required field: principal_dn|principal_username", {"field": "principal_dn"}

    conn = None
    try:
        conn = ldap_client.connect(
            host=host,
            port=port,
            use_ssl=(protocol == "ldaps"),
            verify_tls=verify_tls,
            timeout=timeout,
        )
        if not ldap_client.bind(conn, bind_dn=bind_dn, password=password):
            return False, "LDAP bind failed", {"host": host, "port": port}

        resolved_group_dn = _resolve_group_dn(conn, base_dn=base_dn, group_ref=group_ref)
        resolved_principal_dn = _resolve_principal_dn(
            conn,
            base_dn=base_dn,
            principal_dn=principal_dn,
            principal_username=principal_username,
        )

        conn.search(
            search_base=resolved_group_dn,
            search_filter="(objectClass=group)",
            search_scope=BASE,
            attributes=["member"],
            size_limit=1,
        )
        if conn.entries:
            members = getattr(conn.entries[0], "entry_attributes_as_dict", {}).get("member") or []
            member_lc = {str(v).strip().lower() for v in members if str(v).strip()}
            if resolved_principal_dn.lower() not in member_lc:
                return True, "AD group membership already absent", {
                    "ok": True,
                    "removed": False,
                    "reason": "already_absent",
                    "group_dn": resolved_group_dn,
                    "principal_dn": resolved_principal_dn,
                    "operation": "remove_ad_group_member",
                }

        ok = conn.modify(
            resolved_group_dn,
            {"member": [(MODIFY_DELETE, [resolved_principal_dn])]},
        )
        if not ok:
            result = dict(getattr(conn, "result", {}) or {})
            desc = str(result.get("description") or "").lower()
            msg = str(result.get("message") or "").lower()
            if "no_such_attribute" in desc or "not" in msg:
                return True, "AD group membership already absent", {
                    "ok": True,
                    "removed": False,
                    "reason": "already_absent",
                    "group_dn": resolved_group_dn,
                    "principal_dn": resolved_principal_dn,
                    "operation": "remove_ad_group_member",
                }
            return False, "LDAP group membership remove failed", {
                "group_dn": resolved_group_dn,
                "principal_dn": resolved_principal_dn,
                "error": str(result)[:2000],
            }

        return True, "AD group membership removed", {
            "ok": True,
            "removed": True,
            "reason": "removed",
            "group_dn": resolved_group_dn,
            "principal_dn": resolved_principal_dn,
            "operation": "remove_ad_group_member",
        }
    except Exception as exc:
        return False, "LDAP group membership remove failed", {"error": str(exc)[:2000]}
    finally:
        try:
            if conn is not None:
                conn.unbind()
        except Exception:
            pass
