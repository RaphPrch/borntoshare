from __future__ import annotations

import re
from typing import Any

from app.shared import ldap_client


def search_ldap_principals(params: dict[str, Any]):
    host = str(params.get("host") or "").strip()
    username = str(params.get("username") or "").strip()
    password = str(params.get("password") or "")
    base_dn = str(params.get("base_dn") or "").strip()
    query = str(params.get("query") or "").strip()

    use_ssl = bool(params.get("use_ssl", False))
    port = int(params.get("port", 636 if use_ssl else 389))
    timeout = int(params.get("timeout", 5))
    timeout = max(1, min(timeout, 5))
    limit = int(params.get("limit", 25))
    limit = max(1, min(limit, 5000))
    principal_type = str(params.get("principal_type") or "all").strip().lower()
    if principal_type not in {"all", "user", "group"}:
        principal_type = "all"

    if not host:
        return False, "Missing LDAP host", {"field": "host"}
    if not username:
        return False, "Missing LDAP bind username", {"field": "username"}
    if not password:
        return False, "Missing LDAP bind password", {"field": "password"}
    if not base_dn:
        return False, "Missing LDAP base_dn", {"field": "base_dn"}

    escaped = (
        query.replace("\\", "\\5c")
        .replace("*", "\\2a")
        .replace("(", "\\28")
        .replace(")", "\\29")
        .replace("\x00", "")
    )
    wildcard = f"*{escaped}*" if escaped else "*"

    user_filter = (
        f"(&"
        f"(objectClass=user)"
        f"(!(objectClass=computer))"
        f"(!(sAMAccountName=*$))"
        f"(|(cn={wildcard})(displayName={wildcard})(givenName={wildcard})(sn={wildcard})(sAMAccountName={wildcard})(userPrincipalName={wildcard})(mail={wildcard}))"
        f")"
    )
    group_filter = f"(&(objectClass=group)(|(cn={wildcard})(sAMAccountName={wildcard})))"

    if principal_type == "user":
        search_filter = user_filter
    elif principal_type == "group":
        search_filter = group_filter
    else:
        search_filter = f"(|{user_filter}{group_filter})"

    attrs = [
        "cn",
        "displayName",
        "givenName",
        "sn",
        "distinguishedName",
        "sAMAccountName",
        "userPrincipalName",
        "mail",
        "objectClass",
        "objectGUID",
        "member",
        "memberOf",
        "userAccountControl",
    ]

    conn = None
    try:
        conn = ldap_client.connect(
            host=host,
            port=port,
            use_ssl=use_ssl,
            verify_tls=bool(params.get("verify_tls", False)),
            timeout=timeout,
        )
        if not ldap_client.bind(conn, bind_dn=username, password=password):
            return False, "LDAP search failed", {"host": host, "port": port, "error": "bind_failed"}

        ldap_client.search(
            conn,
            base_dn=base_dn,
            search_filter=search_filter,
            attributes=attrs,
            limit=limit,
            scope=str(params.get("search_scope") or "subtree"),
        )

        items: list[dict[str, Any]] = []
        for entry in conn.entries:
            data = entry.entry_attributes_as_dict or {}
            object_classes = [str(v).lower() for v in (data.get("objectClass") or [])]
            principal_type = "group" if "group" in object_classes else "user"

            account_name = str((data.get("sAMAccountName") or [""])[0] or "").strip()
            display_name = str((data.get("displayName") or data.get("cn") or [""])[0] or "").strip()
            dn = str((data.get("distinguishedName") or [""])[0] or "").strip()
            if principal_type == "user" and account_name.endswith("$"):
                # AD computer accounts should not be exposed in identity import UI
                continue
            email = str((data.get("mail") or [""])[0] or "").strip() or None
            upn = str((data.get("userPrincipalName") or [""])[0] or "").strip() or None
            external_id = str((data.get("objectGUID") or [""])[0] or "").strip() or dn or account_name
            member_of = [str(v).strip() for v in (data.get("memberOf") or []) if str(v).strip()]
            member_dns = [str(v).strip() for v in (data.get("member") or []) if str(v).strip()]

            uac_raw = (data.get("userAccountControl") or [None])[0]
            try:
                uac = int(uac_raw) if uac_raw is not None else None
            except (TypeError, ValueError):
                uac = None
            enabled = None if uac is None else (uac & 2) == 0
            status = "enabled" if enabled is True else "disabled" if enabled is False else None

            group_names = []
            for gdn in member_of:
                m = re.match(r"(?i)^CN=([^,]+)", gdn)
                group_names.append(m.group(1) if m else gdn)

            items.append(
                {
                    "id": external_id,
                    "type": principal_type,
                    "username": account_name or None,
                    "display_name": display_name or account_name or dn,
                    "email": email,
                    "upn": upn,
                    "auth_source": "ad",
                    "external_id": external_id,
                    "dn": dn,
                    "status": status,
                    "group_dns": member_of if principal_type == "user" else [],
                    "group_names": group_names if principal_type == "user" else [],
                    "member_dns": member_dns if principal_type == "group" else [],
                }
            )

        return True, "LDAP search successful", {"count": len(items), "items": items}
    except Exception as e:
        return False, "LDAP search failed", {"host": host, "port": port, "error": str(e)[:2000]}
    finally:
        try:
            if conn is not None:
                conn.unbind()
        except Exception:
            pass
