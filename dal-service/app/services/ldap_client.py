from __future__ import annotations

from typing import Any

# V1 boundary:
# - DAL keeps only the LDAP connectivity primitive required by snapshot ingestion.
# - Live AD/LDAP business operations are orchestrated by Governance -> Capsule Runner.

try:
    from ldap3 import ALL, Connection, Server  # type: ignore

    _HAS_LDAP3 = True
except Exception:
    _HAS_LDAP3 = False


class LdapClientError(RuntimeError):
    pass


def _require_ldap3() -> None:
    if not _HAS_LDAP3:
        raise LdapClientError(
            "ldap3 is not installed in dal-service image. "
            "Add dependency 'ldap3' to enable AD connectivity."
        )


def _open_connection(
    *,
    host: str,
    port: int,
    protocol: str,
    bind_dn: str,
    bind_password: str,
    authentication: Any | None = None,
):
    _require_ldap3()
    use_ssl = str(protocol or "").strip().lower() == "ldaps"
    server = Server(str(host or "").strip(), port=int(port), use_ssl=use_ssl, get_info=ALL)
    kwargs: dict[str, Any] = {}
    if authentication is not None:
        kwargs["authentication"] = authentication
    return Connection(
        server,
        user=str(bind_dn or "").strip(),
        password=str(bind_password or ""),
        auto_bind=True,
        **kwargs,
    )

