from __future__ import annotations

from collections import deque
from typing import Any

from ldap3 import BASE, SUBTREE

from app.shared import ldap_client


def _entry_get(entry: Any, key: str) -> Any:
    data = getattr(entry, "entry_attributes_as_dict", {}) or {}
    value = data.get(key)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _entry_get_list(entry: Any, key: str) -> list[Any]:
    data = getattr(entry, "entry_attributes_as_dict", {}) or {}
    value = data.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _escape_filter(value: str) -> str:
    text = str(value or "")
    return (
        text.replace("\\", "\\5c")
        .replace("*", "\\2a")
        .replace("(", "\\28")
        .replace(")", "\\29")
        .replace("\x00", "")
    )


def _resolve_group_dn(conn: Any, *, base_dn: str, group_ref: str) -> str:
    raw = str(group_ref or "").strip()
    if not raw:
        raise ValueError("root_group_dn is required")

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


def discover_group_users_recursive(params: dict[str, Any]):
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
    base_dn = str(params.get("base_dn") or "").strip()
    root_group_dn = str(params.get("root_group_dn") or "").strip()
    max_depth = int(params.get("max_depth") or 10)
    max_depth = max(1, min(max_depth, 30))

    if not host:
        return False, "Missing required field: host", {"field": "host"}
    if not bind_dn:
        return False, "Missing required field: bind_dn", {"field": "bind_dn"}
    if not password:
        return False, "Missing required field: password", {"field": "password"}
    if not base_dn:
        return False, "Missing required field: base_dn", {"field": "base_dn"}
    if not root_group_dn:
        return False, "Missing required field: root_group_dn", {"field": "root_group_dn"}

    conn = None
    try:
        conn = ldap_client.connect(
            host=host,
            port=port,
            use_ssl=(protocol == "ldaps"),
            verify_tls=bool(params.get("verify_tls", False)),
            timeout=timeout,
        )
        if not ldap_client.bind(conn, bind_dn=bind_dn, password=password):
            return False, "LDAP bind failed", {"host": host, "port": port}

        resolved_root_group_dn = _resolve_group_dn(conn, base_dn=base_dn, group_ref=root_group_dn)
        visited_groups: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(resolved_root_group_dn, 0)])
        users_by_dn: dict[str, dict[str, Any]] = {}

        while queue:
            group_dn, depth = queue.popleft()
            key = str(group_dn).strip().lower()
            if not key or key in visited_groups:
                continue
            visited_groups.add(key)

            conn.search(
                search_base=group_dn,
                search_filter="(objectClass=group)",
                search_scope=BASE,
                attributes=["member", "distinguishedName"],
                size_limit=1,
            )
            if not conn.entries:
                continue

            members = _entry_get_list(conn.entries[0], "member")
            for member_dn in members:
                member_dn = str(member_dn or "").strip()
                if not member_dn:
                    continue

                conn.search(
                    search_base=member_dn,
                    search_filter="(objectClass=*)",
                    search_scope=BASE,
                    attributes=[
                        "objectClass",
                        "distinguishedName",
                        "cn",
                        "displayName",
                        "sAMAccountName",
                        "userPrincipalName",
                        "mail",
                    ],
                    size_limit=1,
                )
                if not conn.entries:
                    continue

                entry = conn.entries[0]
                classes = {str(v).lower() for v in _entry_get_list(entry, "objectClass") if str(v).strip()}

                if "group" in classes:
                    if depth < max_depth:
                        next_group_dn = str(_entry_get(entry, "distinguishedName") or member_dn).strip()
                        if next_group_dn:
                            queue.append((next_group_dn, depth + 1))
                    continue

                if "user" not in classes and "person" not in classes:
                    continue
                if "computer" in classes:
                    continue

                dn = str(_entry_get(entry, "distinguishedName") or member_dn).strip()
                if not dn:
                    continue

                username = str(
                    _entry_get(entry, "sAMAccountName")
                    or _entry_get(entry, "userPrincipalName")
                    or _entry_get(entry, "cn")
                    or dn
                ).strip()
                users_by_dn[dn] = {
                    "id": dn,
                    "external_id": dn,
                    "dn": dn,
                    "username": username,
                    "display_name": str(_entry_get(entry, "displayName") or _entry_get(entry, "cn") or username).strip(),
                    "email": str(_entry_get(entry, "mail") or "").strip() or None,
                    "type": "user",
                }

        users = list(users_by_dn.values())
        return True, "Recursive group users discovery successful", {
            "count": len(users),
            "items": users,
            "users": users,
            "root_group_dn": resolved_root_group_dn,
            "visited_groups": len(visited_groups),
            "max_depth": max_depth,
            "operation": "discover_group_users_recursive",
        }
    except Exception as exc:
        return False, "LDAP recursive group users discovery failed", {
            "host": host,
            "port": port,
            "error": str(exc)[:2000],
        }
    finally:
        try:
            if conn is not None:
                conn.unbind()
        except Exception:
            pass

