"""Connection test of an LDAP / Active Directory identity source, step by step.

connect (TCP, then TLS for ldaps) -> bind with the service account -> read the base DN.
Each step is reported (tls_ok, bind_ok, base_dn_ok, duration_ms) with a failure_code and a hint,
so the UI tells the administrator what to fix.
"""
from __future__ import annotations

import socket
import time

from ldap3 import BASE

from app.shared import ldap_client

__test__ = False

# Active Directory sub-codes of invalidCredentials ("... data 52e, v4563")
_AD_BIND_REASONS = {
    "525": ("LDAP_ACCOUNT_NOT_FOUND", "The service account does not exist in the directory."),
    "52e": ("LDAP_BIND_FAILED", "Wrong password or bind DN for the service account."),
    "530": ("LDAP_ACCOUNT_RESTRICTED", "The service account may not sign in at this time."),
    "531": ("LDAP_ACCOUNT_RESTRICTED", "The service account may not sign in from this workstation."),
    "532": ("LDAP_PASSWORD_EXPIRED", "The password of the service account has expired."),
    "533": ("LDAP_ACCOUNT_DISABLED", "The service account is disabled."),
    "701": ("LDAP_ACCOUNT_EXPIRED", "The service account has expired."),
    "773": ("LDAP_PASSWORD_EXPIRED", "The password of the service account must be changed."),
    "775": ("LDAP_ACCOUNT_LOCKED", "The service account is locked out."),
}


def _bind_failure(raw_result: dict) -> tuple[str, str]:
    description = str(raw_result.get("description") or "").strip()
    message = str(raw_result.get("message") or "").lower()
    if description == "strongerAuthRequired":
        return (
            "LDAP_SIGNING_REQUIRED",
            "The domain controller requires signed LDAP: enable LDAPS (port 636) on the identity source.",
        )
    for code, reason in _AD_BIND_REASONS.items():
        if f"data {code}" in message:
            return reason
    return "LDAP_BIND_FAILED", "Wrong password or bind DN for the service account."


def _connect_failure(error: Exception, use_ssl: bool) -> tuple[str, str]:
    text = str(error).lower()
    if any(word in text for word in ("certificate", "ssl", "tls", "ca certificate file")):
        return (
            "LDAP_TLS_FAILED",
            "The certificate of the domain controller was refused: fetch the certificate again or check the authority of the directory, and use the host name of the certificate.",
        )
    if any(word in text for word in ("name or service not known", "nodename nor servname", "getaddrinfo", "no address", "invalid server address")):
        return "LDAP_DNS_FAILED", "The host name of the domain controller cannot be resolved (DNS)."
    if "timed out" in text or "timeout" in text:
        return "LDAP_UNREACHABLE", "The domain controller did not answer in time (network, firewall)."
    port = "636" if use_ssl else "389"
    return "LDAP_UNREACHABLE", f"The domain controller refused the connection: check the host and that port {port} is open."


def test_ldap_bind(params: dict):
    host = str(params.get("host") or "").strip()
    username = str(params.get("username") or "").strip()
    password = str(params.get("password") or "")
    base_dn = str(params.get("base_dn") or "").strip()
    use_ssl = bool(params.get("use_ssl", False))
    port = int(params.get("port", 636 if use_ssl else 389))
    timeout = max(1, min(int(params.get("timeout", 10)), 15))

    if not host:
        return False, "Missing LDAP host", {"field": "host", "failure_code": "LDAP_MISSING_FIELD", "retryable": False}
    if not username:
        return False, "Missing LDAP bind username", {"field": "username", "failure_code": "LDAP_MISSING_FIELD", "retryable": False}
    if not password:
        return False, "Missing LDAP bind password", {"field": "password", "failure_code": "LDAP_MISSING_FIELD", "retryable": False}

    started = time.monotonic()

    details: dict = {
        "host": host,
        "port": port,
        "use_ssl": use_ssl,
        "tls_verified": bool(use_ssl and params.get("verify_tls")),
        "tls_ok": None,
        "bind_ok": None,
        "base_dn_ok": None,
    }

    def _done(ok: bool, message: str, **extra):
        details.update(extra)
        details["duration_ms"] = int((time.monotonic() - started) * 1000)
        if not ok:
            details.setdefault("retryable", False)
        return ok, message, details

    # Resolve first: a clear DNS diagnosis, without ldap3 retrying every address family
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        hint = "The host name of the domain controller cannot be resolved (DNS)."
        return _done(False, hint, failure_code="LDAP_DNS_FAILED", hint=hint, error=str(exc)[:500])

    conn = None
    try:
        try:
            conn = ldap_client.connect(
                host=host,
                port=port,
                use_ssl=use_ssl,
                verify_tls=bool(params.get("verify_tls")),
                timeout=timeout,
                ca_pem=params.get("tls_ca_pem"),
                server_name=params.get("tls_server_name"),
            )
            conn.open()
        except Exception as exc:
            code, hint = _connect_failure(exc, use_ssl)
            if code == "LDAP_TLS_FAILED":
                details["tls_ok"] = False
            return _done(False, hint, failure_code=code, hint=hint, error=str(exc)[:2000])
        if use_ssl:
            details["tls_ok"] = True

        if not ldap_client.bind(conn, bind_dn=username, password=password):
            raw_result = dict(getattr(conn, "result", {}) or {})
            code, hint = _bind_failure(raw_result)
            details["bind_ok"] = False
            return _done(False, hint, failure_code=code, hint=hint, ldap_result=raw_result)
        details["bind_ok"] = True

        if base_dn:
            found = conn.search(search_base=base_dn, search_filter="(objectClass=*)", search_scope=BASE, attributes=["distinguishedName"])
            details["base_dn_ok"] = bool(found)
            if not found:
                description = str(dict(getattr(conn, "result", {}) or {}).get("description") or "")
                hint = (
                    "The base DN does not exist in the directory."
                    if description == "noSuchObject"
                    else "The service account cannot read the base DN."
                )
                return _done(False, hint, failure_code="LDAP_BASE_DN_NOT_FOUND", hint=hint)

        return _done(True, "LDAP connection, bind and base DN OK" if base_dn else "LDAP bind successful")
    except Exception as exc:
        code, hint = _connect_failure(exc, use_ssl)
        return _done(False, hint, failure_code=code, hint=hint, error=str(exc)[:2000])
    finally:
        try:
            if conn is not None:
                conn.unbind()
        except Exception:
            pass
