"""What a directory says about itself before any account is given: encryption, certificate, type and base.

Nothing here is trusted: the values fill the form, and the administrator still accepts the certificate.
"""
from __future__ import annotations

from typing import Any

from ldap3 import BASE

from app.actions.tls_certificate import fetch_tls_certificate
from app.shared import ldap_client

_AD_CAPABILITY = "1.2.840.113556.1.4.800"
_ROOT_ATTRIBUTES = ["defaultNamingContext", "namingContexts", "supportedCapabilities", "forestFunctionality"]


def _values(entry: dict[str, Any], name: str) -> list[str]:
    value = entry.get(name)
    if value is None:
        return []
    return [str(item) for item in value] if isinstance(value, (list, tuple)) else [str(value)]


def describe_root(entry: dict[str, Any]) -> dict[str, str | None]:
    """Directory type and search base from a root DSE entry."""
    is_ad = _AD_CAPABILITY in _values(entry, "supportedCapabilities") or bool(_values(entry, "forestFunctionality"))
    defaults = _values(entry, "defaultNamingContext")
    contexts = [c for c in _values(entry, "namingContexts") if not c.lower().startswith(("cn=configuration", "cn=schema", "dc=forestdnszones", "dc=domaindnszones", "cn=config", "cn=monitor"))]
    return {
        "flavor": "ad" if is_ad else "openldap",
        "base_dn": (defaults or contexts or [None])[0],
    }


def _read_root(host: str, port: int, use_ssl: bool, timeout: int) -> dict[str, Any] | None:
    """Root DSE read anonymously; None when the server refuses it or does not speak LDAP."""
    conn = None
    try:
        conn = ldap_client.connect(host=host, port=port, use_ssl=use_ssl, verify_tls=False, timeout=timeout)
        conn.open()
        if not conn.search(search_base="", search_filter="(objectClass=*)", search_scope=BASE, attributes=_ROOT_ATTRIBUTES):
            return None
        return dict(conn.response[0].get("attributes") or {})
    except Exception:
        return None
    finally:
        try:
            if conn is not None:
                conn.unbind()
        except Exception:
            pass


def discover_directory(params: dict[str, Any]):
    host = str(params.get("host") or "").strip()
    timeout = max(1, min(int(params.get("timeout") or 5), 15))
    if not host:
        return False, "Missing LDAP host", {"failure_code": "DISCOVERY_HOST_MISSING"}

    certificate_ok, _message, certificate = fetch_tls_certificate({"host": host, "port": 636, "timeout": timeout})
    use_ssl = bool(certificate_ok)
    port = 636 if use_ssl else 389
    root = _read_root(host, port, use_ssl, timeout)

    if not use_ssl and root is None:
        return False, "The directory did not answer on port 636 or 389: check the host and the firewall", {
            "host": host, "failure_code": "DISCOVERY_UNREACHABLE",
        }

    description = describe_root(root) if root is not None else {"flavor": None, "base_dn": None}
    return True, "Directory analysed", {
        "host": host,
        "protocol": "ldaps" if use_ssl else "ldap",
        "port": port,
        **description,
        "certificate": certificate if use_ssl else None,
    }
