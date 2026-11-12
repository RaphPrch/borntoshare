from __future__ import annotations

import ssl
from typing import Any

from ldap3 import ALL, BASE, FIRST, LEVEL, SIMPLE, SUBTREE, Connection, Server, ServerPool, Tls
from ldap3.core.exceptions import LDAPSSLConfigurationError


def tls_config(verify_tls: bool, ca_pem: str | None = None, server_name: str | None = None) -> Tls:
    """Certificate check set on the directory: its CA (PEM) and, for a host given by IP, the name in the certificate."""
    if not verify_tls:
        return Tls(validate=ssl.CERT_NONE)
    try:
        return Tls(
            validate=ssl.CERT_REQUIRED,
            ca_certs_data=(ca_pem or "").strip() or None,
            valid_names=[server_name.strip()] if (server_name or "").strip() else None,
        )
    except Exception as exc:
        raise LDAPSSLConfigurationError(f"Invalid LDAP CA certificate: {exc}") from exc


def hosts_of(value: str | None) -> list[str]:
    """Domain controllers of a directory: « AD01.corp.local, AD02.corp.local » (commas, semicolons or spaces), in order."""
    import re

    return [part for part in re.split(r"[,;\s]+", str(value or "").strip()) if part]


def _server(name: str, *, port: int, use_ssl: bool, verify_tls: bool, timeout: int, ca_pem: str | None, server_name: str | None) -> Server:
    from app.shared.name_resolution import address_for_tools

    address = address_for_tools(name)
    # Reached by its address, the server keeps its name for the certificate check
    if address != name and not (server_name or "").strip():
        server_name = name
    tls = tls_config(verify_tls, ca_pem, server_name) if use_ssl else None
    return Server(address, port=int(port), use_ssl=bool(use_ssl), get_info=ALL, connect_timeout=int(timeout), tls=tls)


def server_or_pool(*, host: str, port: int, use_ssl: bool, verify_tls: bool, timeout: int, ca_pem: str | None = None,
                   server_name: str | None = None):
    """One server, or several controllers tried in order (the first that answers is used: ldap3 ServerPool FIRST)."""
    names = hosts_of(host) or [str(host or "").strip()]
    servers = [_server(name, port=port, use_ssl=use_ssl, verify_tls=verify_tls, timeout=timeout, ca_pem=ca_pem,
                       server_name=server_name) for name in names]
    if len(servers) == 1:
        return servers[0]
    return ServerPool(servers, FIRST, active=1, exhaust=False)


def connect(
    *,
    host: str,
    port: int,
    use_ssl: bool,
    verify_tls: bool,
    timeout: int,
    ca_pem: str | None = None,
    server_name: str | None = None,
) -> Connection:
    server = server_or_pool(host=host, port=port, use_ssl=use_ssl, verify_tls=verify_tls, timeout=timeout, ca_pem=ca_pem,
                            server_name=server_name)
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
