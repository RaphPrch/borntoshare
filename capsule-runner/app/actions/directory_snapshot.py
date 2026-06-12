from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.shared import ldap_client


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_usn(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(str(value).strip())
    except Exception:
        return None


def _safe_dt(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    raw = str(value).strip()
    if not raw:
        return None

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        pass

    for pattern in ("%Y%m%d%H%M%S.%fZ", "%Y%m%d%H%M%SZ"):
        try:
            dt = datetime.strptime(raw, pattern).replace(tzinfo=timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")
        except Exception:
            continue

    return None


def _row_attr(row: Any, key: str) -> Any:
    data = getattr(row, "entry_attributes_as_dict", {}) or {}
    value = data.get(key)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _norm_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_text(value: Any, max_len: int) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    return raw[: max(1, int(max_len))]


def collect_directory_snapshot(params: dict[str, Any]):
    snapshot_id = _as_int(params.get("snapshot_id"), 0)
    source_id = _as_int(params.get("identity_source_id"), 0)
    host = str(params.get("host") or "").strip()
    bind_dn = str(params.get("bind_dn") or params.get("username") or "").strip()
    password = str(params.get("password") or "")
    base_dn = str(params.get("base_dn") or "").strip()
    protocol = str(params.get("protocol") or "ldaps").strip().lower()
    use_ssl = bool(params.get("use_ssl", protocol == "ldaps"))
    verify_tls = bool(params.get("verify_tls", False))
    port = _as_int(params.get("port"), 636 if use_ssl else 389)
    timeout = max(1, min(_as_int(params.get("timeout"), 15), 30))

    if snapshot_id <= 0:
        return False, "Missing required field: snapshot_id", {"field": "snapshot_id"}
    if source_id <= 0:
        return False, "Missing required field: identity_source_id", {"field": "identity_source_id"}
    if not host:
        return False, "Missing required field: host", {"field": "host"}
    if not bind_dn:
        return False, "Missing required field: bind_dn", {"field": "bind_dn"}
    if not password:
        return False, "Missing required field: password", {"field": "password"}
    if not base_dn:
        return False, "Missing required field: base_dn", {"field": "base_dn"}

    conn = None
    try:
        conn = ldap_client.connect(
            host=host,
            port=port,
            use_ssl=use_ssl,
            verify_tls=verify_tls,
            timeout=timeout,
        )
        if not ldap_client.bind(conn, bind_dn=bind_dn, password=password):
            return False, "LDAP bind failed", {"snapshot_id": snapshot_id, "host": host, "port": port}

        user_attrs = [
            "distinguishedName",
            "cn",
            "displayName",
            "sAMAccountName",
            "userPrincipalName",
            "mail",
            "objectGUID",
            "objectSid",
            "whenChanged",
            "uSNChanged",
        ]
        group_attrs = [
            "distinguishedName",
            "cn",
            "sAMAccountName",
            "description",
            "objectGUID",
            "whenChanged",
            "uSNChanged",
            "member",
        ]

        ldap_client.search(
            conn,
            base_dn=base_dn,
            search_filter="(&(objectClass=user)(!(objectClass=computer))(!(sAMAccountName=*$)))",
            attributes=user_attrs,
            limit=5000,
            scope="subtree",
        )
        user_rows = list(getattr(conn, "entries", []) or [])

        users: list[dict[str, Any]] = []
        user_external_by_dn: dict[str, str] = {}
        user_external_by_key: dict[str, str] = {}
        for entry in user_rows:
            dn = str(_row_attr(entry, "distinguishedName") or getattr(entry, "entry_dn", "") or "").strip()
            external_id = _safe_text(_row_attr(entry, "objectGUID") or dn or _row_attr(entry, "sAMAccountName"), 255)
            if not external_id:
                continue
            dn_key = _norm_key(dn)
            if dn_key:
                user_external_by_dn[dn_key] = external_id

            for key in (
                external_id,
                _row_attr(entry, "objectGUID"),
                _row_attr(entry, "objectSid"),
                _row_attr(entry, "userPrincipalName"),
                _row_attr(entry, "sAMAccountName"),
                dn,
            ):
                norm = _norm_key(key)
                if norm:
                    user_external_by_key[norm] = external_id

            users.append(
                {
                    "external_id": external_id,
                    "object_guid": _safe_text(_row_attr(entry, "objectGUID"), 36),
                    "object_sid": _safe_text(_row_attr(entry, "objectSid"), 190),
                    "upn": _safe_text(_row_attr(entry, "userPrincipalName"), 255),
                    "dn": _safe_text(dn, 512),
                    "when_changed": _safe_dt(_row_attr(entry, "whenChanged")),
                    "usn_changed": _safe_usn(_row_attr(entry, "uSNChanged")),
                    "username": _safe_text(_row_attr(entry, "sAMAccountName"), 190),
                    "display_name": _safe_text(_row_attr(entry, "displayName") or _row_attr(entry, "cn"), 190),
                    "email": _safe_text(_row_attr(entry, "mail"), 255),
                    "source": _safe_text("capsule_snapshot", 64),
                    "is_active": True,
                }
            )

        ldap_client.search(
            conn,
            base_dn=base_dn,
            search_filter="(objectClass=group)",
            attributes=group_attrs,
            limit=5000,
            scope="subtree",
        )
        group_rows = list(getattr(conn, "entries", []) or [])

        groups: list[dict[str, Any]] = []
        group_external_by_dn: dict[str, str] = {}
        group_external_by_key: dict[str, str] = {}
        group_members_raw: list[tuple[str, str]] = []
        memberships: list[dict[str, Any]] = []
        for entry in group_rows:
            dn = str(_row_attr(entry, "distinguishedName") or getattr(entry, "entry_dn", "") or "").strip()
            external_id = _safe_text(_row_attr(entry, "objectGUID") or dn or _row_attr(entry, "sAMAccountName"), 255)
            if not external_id:
                continue

            dn_key = _norm_key(dn)
            if dn_key:
                group_external_by_dn[dn_key] = external_id
            for key in (
                external_id,
                _row_attr(entry, "objectGUID"),
                _row_attr(entry, "sAMAccountName"),
                dn,
            ):
                norm = _norm_key(key)
                if norm:
                    group_external_by_key[norm] = external_id

            groups.append(
                {
                    "external_id": external_id,
                    "dn": _safe_text(dn, 512),
                    "when_changed": _safe_dt(_row_attr(entry, "whenChanged")),
                    "usn_changed": _safe_usn(_row_attr(entry, "uSNChanged")),
                    "name": _safe_text(_row_attr(entry, "cn"), 255),
                    "code": _safe_text(_row_attr(entry, "sAMAccountName"), 255),
                    "description": _safe_text(_row_attr(entry, "description"), 4096),
                    "is_active": True,
                }
            )

            members = (_row_attr(entry, "member") or [])
            if not isinstance(members, list):
                members = [members]
            for member_dn in members:
                member_ref = str(member_dn or "").strip()
                if not member_ref:
                    continue

                # Keep raw and normalize in a second pass so nested group refs can be
                # resolved regardless of LDAP return order.
                group_members_raw.append((external_id, member_ref))

        seen_memberships: set[tuple[str, str, str]] = set()
        for group_external_id, member_ref in group_members_raw:
            member_key = _norm_key(member_ref)
            if not member_key:
                continue

            member_external_id = user_external_by_dn.get(member_key) or user_external_by_key.get(member_key)
            member_type = "user"

            if not member_external_id:
                member_external_id = group_external_by_dn.get(member_key) or group_external_by_key.get(member_key)
                member_type = "group"

            if not member_external_id:
                # Ignore unresolved members to avoid writing non-joinable memberships.
                continue

            group_external_id = _safe_text(group_external_id, 255)
            member_external_id = _safe_text(member_external_id, 255)
            if not group_external_id or not member_external_id:
                continue

            tuple_key = (group_external_id, member_external_id, member_type)
            if tuple_key in seen_memberships:
                continue
            seen_memberships.add(tuple_key)

            memberships.append(
                {
                    "group_external_id": group_external_id,
                    "member_external_id": member_external_id,
                    "member_type": member_type,
                }
            )

        payload = {
            "users": users,
            "groups": groups,
            "memberships": memberships,
        }
        return True, "Directory snapshot collected", {
            "snapshot_id": snapshot_id,
            "identity_source_id": source_id,
            "payload": payload,
            "counts": {
                "users": len(users),
                "groups": len(groups),
                "memberships": len(memberships),
            },
            "collected_at": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as exc:
        return False, "Directory snapshot collection failed", {
            "snapshot_id": snapshot_id,
            "identity_source_id": source_id,
            "error": str(exc)[:2000],
        }
    finally:
        try:
            if conn is not None:
                conn.unbind()
        except Exception:
            pass
