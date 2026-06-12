from __future__ import annotations

import ssl
from typing import Any

from ldap3 import ALL, BASE, LEVEL, SIMPLE, SUBTREE, Connection, Server, Tls


def connect(*, host: str, port: int, use_ssl: bool, verify_tls: bool, timeout: int) -> Connection:
    tls = Tls(validate=ssl.CERT_REQUIRED if verify_tls else ssl.CERT_NONE) if use_ssl else None
    server = Server(
        str(host or "").strip(),
        port=int(port),
        use_ssl=bool(use_ssl),
        get_info=ALL,
        connect_timeout=int(timeout),
        tls=tls,
    )
    return Connection(server, auto_bind=False, receive_timeout=int(timeout))


def bind(conn: Connection, *, bind_dn: str, password: str) -> bool:
    user = str(bind_dn or "").strip()
    pwd = str(password or "")
    # Force SIMPLE auth explicitly to avoid anonymous bind mode when the
    # connection was created without credentials.
    return bool(conn.rebind(user=user, password=pwd, authentication=SIMPLE))


def search(
    conn: Connection,
    *,
    base_dn: str,
    search_filter: str,
    attributes: list[str],
    limit: int,
    scope: str = "subtree",
) -> list[dict[str, Any]]:
    normalized = str(scope or "subtree").strip().lower()
    ldap_scope = SUBTREE
    if normalized in {"base"}:
        ldap_scope = BASE
    elif normalized in {"one", "onelevel", "children"}:
        ldap_scope = LEVEL

    conn.search(
        search_base=str(base_dn or "").strip(),
        search_filter=str(search_filter or "").strip(),
        search_scope=ldap_scope,
        attributes=list(attributes or []),
        size_limit=max(1, int(limit or 1)),
    )
    out: list[dict[str, Any]] = []
    for entry in conn.entries:
        out.append(dict(getattr(entry, "entry_attributes_as_dict", {}) or {}))
    return out


def create_group(
    conn: Connection,
    *,
    group_dn: str,
    group_name: str,
    description_text: str | None = None,
) -> bool:
    attrs: dict[str, Any] = {
        "sAMAccountName": str(group_name or "").strip(),
        "groupType": -2147483646,
    }
    description = str(description_text or "").strip()
    if description:
        attrs["description"] = description
    return bool(conn.add(str(group_dn or "").strip(), ["top", "group"], attrs))


def add_membership(conn: Connection, *, group_dn: str, member_dn: str) -> bool:
    from ldap3 import MODIFY_ADD

    return bool(
        conn.modify(
            str(group_dn or "").strip(),
            {"member": [(MODIFY_ADD, [str(member_dn or "").strip()])]},
        )
    )
