from __future__ import annotations

from app.shared import ldap_client

__test__ = False


def test_ldap_bind(params: dict):
    host = str(params.get("host") or "").strip()
    username = str(params.get("username") or "").strip()
    password = str(params.get("password") or "")
    use_ssl = bool(params.get("use_ssl", False))
    port = int(params.get("port", 636 if use_ssl else 389))
    timeout = int(params.get("timeout", 5))
    timeout = max(1, min(timeout, 5))
    verify_tls = bool(params.get("verify_tls", False))

    if not host:
        return False, "Missing LDAP host", {"field": "host"}
    if not username:
        return False, "Missing LDAP bind username", {"field": "username"}
    if not password:
        return False, "Missing LDAP bind password", {"field": "password"}

    conn = None
    try:
        conn = ldap_client.connect(
            host=host,
            port=port,
            use_ssl=use_ssl,
            verify_tls=verify_tls,
            timeout=timeout,
        )
        if not ldap_client.bind(conn, bind_dn=username, password=password):
            raw_result = dict(getattr(conn, "result", {}) or {})
            ldap_description = str(raw_result.get("description") or "").strip()
            ldap_message = str(raw_result.get("message") or "").strip()
            msg = "LDAP bind failed"
            if ldap_description:
                msg = f"{msg}: {ldap_description}"
            if ldap_message:
                msg = f"{msg} ({ldap_message})"
            return False, msg, {
                "host": host,
                "port": port,
                "use_ssl": use_ssl,
                "ldap_result": raw_result,
            }
        return True, "LDAP bind successful", {"host": host, "port": port, "use_ssl": use_ssl}
    except Exception as e:
        raw_result = dict(getattr(conn, "result", {}) or {}) if conn is not None else {}
        return False, f"LDAP bind failed: {str(e)[:400]}", {
            "host": host,
            "port": port,
            "use_ssl": use_ssl,
            "error": str(e)[:2000],
            "ldap_result": raw_result,
        }
    finally:
        try:
            if conn is not None:
                conn.unbind()
        except Exception:
            pass
