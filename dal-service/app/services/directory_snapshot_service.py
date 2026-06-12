from __future__ import annotations

import datetime as dt
from typing import Any

from ldap3 import BASE, LEVEL, SUBTREE  # type: ignore
from ldap3.protocol.formatters.formatters import format_sid, format_uuid_le  # type: ignore
from sqlalchemy.orm import Session

from app.models.identity_sources import IdentitySource
from app.repositories.directory_snapshots_repo import DirectorySnapshotsRepo
from app.services.ldap_client import _open_connection
from app.services.secret_broker_client import resolve_secret_ref


LDAP_SCOPE_BY_NAME = {
    "base": BASE,
    "onelevel": LEVEL,
    "one": LEVEL,
    "children": LEVEL,
    "subtree": SUBTREE,
}

USERS_ATTRS = [
    "distinguishedName",
    "cn",
    "sAMAccountName",
    "userPrincipalName",
    "mail",
    "userAccountControl",
    "objectGUID",
    "objectSid",
    "whenChanged",
    "uSNChanged",
]

GROUPS_ATTRS = [
    "distinguishedName",
    "cn",
    "sAMAccountName",
    "objectGUID",
    "objectSid",
    "member",
    "whenChanged",
    "uSNChanged",
]

def _to_datetime(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in (
        "%Y%m%d%H%M%S.0Z",
        "%Y%m%d%H%M%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            return dt.datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        cleaned = raw.replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(cleaned)
        if parsed.tzinfo is not None:
            return parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _ad_user_enabled(attrs: dict[str, Any]) -> bool:
    flags_raw = attrs.get("userAccountControl")
    flags = _to_int(flags_raw)
    if flags is None:
        # Fail-open for compatibility when attribute is unavailable.
        return True
    # ACCOUNTDISABLE bit (0x0002)
    return (int(flags) & 0x0002) == 0


def _to_guid(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        out = str(format_uuid_le(bytes(value))).strip().strip("{}")
        return out or None
    raw = str(value).strip().strip("{}")
    return raw or None


def _to_sid(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        out = str(format_sid(bytes(value))).strip()
        return out or None
    raw = str(value).strip()
    return raw or None


class DirectorySnapshotService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = DirectorySnapshotsRepo(db)

    def run_snapshot(
        self,
        *,
        identity_source_id: int,
        initiated_by: str | None,
        snapshot_source: str | None,
        correlation_id: str | None,
        mode: str | None = "auto",
        force_full: bool = False,
    ) -> dict[str, Any]:
        source = self.db.get(IdentitySource, int(identity_source_id))
        if not source:
            raise ValueError("identity_source_not_found")

        caps = dict(source.capabilities or {})
        requested_mode = str(mode or "auto").strip().lower()
        normalized_mode = self._resolve_mode(
            requested_mode=requested_mode,
            force_full=bool(force_full),
            source=source,
            capabilities=caps,
        )

        active_snapshot = self.repo.get_latest_active(identity_source_id=int(identity_source_id))
        if normalized_mode in {"usn", "whenchanged"} and not active_snapshot:
            normalized_mode = "full"

        bind_password_ref = str(source.bind_password_ref or "").strip()
        if not bind_password_ref:
            raise ValueError("bind_password_ref_required")
        bind_password = resolve_secret_ref(bind_password_ref)
        if not bind_password:
            raise ValueError("bind_password_resolution_failed")

        host = str(source.host or "").strip()
        base_dn = str(source.base_dn or "").strip()
        bind_dn = str(source.bind_dn or "").strip()
        if not host or not base_dn or not bind_dn:
            raise ValueError("identity_source_connection_fields_missing")

        run = self.repo.create_run(
            identity_source_id=int(identity_source_id),
            initiated_by=initiated_by,
            snapshot_source=snapshot_source,
            correlation_id=correlation_id,
            summary_json={
                "mode": normalized_mode,
                "requested_mode": requested_mode,
                "phase": "started",
            },
        )
        snapshot_id = int(run["id"])

        if active_snapshot and normalized_mode in {"dirsync", "usn", "whenchanged"}:
            self.repo.clone_from_snapshot(
                from_snapshot_id=int(active_snapshot["id"]),
                to_snapshot_id=snapshot_id,
            )

        self.repo.patch_status(
            snapshot_id=snapshot_id,
            status="RUNNING",
            summary_json={
                "mode": normalized_mode,
                "requested_mode": requested_mode,
                "page_size": 1000,
            },
            error_message=None,
        )

        conn = _open_connection(
            host=host,
            port=int(source.port or (636 if str(source.protocol or "").lower() == "ldaps" else 389)),
            protocol=str(source.protocol or "ldaps"),
            bind_dn=bind_dn,
            bind_password=bind_password,
        )

        try:
            users, groups, memberships, stats = self._collect_entries(
                conn=conn,
                source=source,
                mode=normalized_mode,
                capabilities=caps,
            )

            counts = self.repo.bulk_upsert(
                snapshot_id=snapshot_id,
                users=users,
                groups=groups,
                memberships=memberships,
            )

            summary = {
                "mode": normalized_mode,
                "counts": counts,
                "watermarks": {
                    "max_usn_changed": stats.get("max_usn_changed"),
                    "dirsync_cookie": stats.get("dirsync_cookie"),
                },
            }
            self.repo.patch_status(
                snapshot_id=snapshot_id,
                status="SUCCEEDED",
                summary_json=summary,
                error_message=None,
            )

            self._update_source_snapshot_metadata(
                source=source,
                snapshot_id=snapshot_id,
                snapshot_version=int(run.get("version") or 0) or None,
                mode=normalized_mode,
                max_usn_changed=stats.get("max_usn_changed"),
                dirsync_cookie=stats.get("dirsync_cookie"),
            )

            return {
                "snapshot_id": snapshot_id,
                "identity_source_id": int(identity_source_id),
                "mode": normalized_mode,
                **counts,
                "max_usn_changed": stats.get("max_usn_changed"),
                "dirsync_cookie": stats.get("dirsync_cookie"),
            }
        except Exception as exc:
            self.repo.patch_status(
                snapshot_id=snapshot_id,
                status="FAILED",
                summary_json={"mode": normalized_mode},
                error_message=str(exc),
            )
            raise
        finally:
            try:
                conn.unbind()
            except Exception:
                pass

    def _resolve_mode(
        self,
        *,
        requested_mode: str,
        force_full: bool,
        source: IdentitySource,
        capabilities: dict[str, Any],
    ) -> str:
        if force_full:
            return "full"

        explicit = {"full", "dirsync", "usn", "whenchanged", "auto"}
        normalized_requested = requested_mode if requested_mode in explicit else "auto"
        if normalized_requested != "auto":
            return normalized_requested

        if bool(source.dirsync_supported) or bool(capabilities.get("dirsync_supported")):
            return "dirsync"
        if bool(source.delta_supported) or bool(capabilities.get("delta_supported")):
            return "usn"
        if source.last_snapshot_version:
            return "whenchanged"
        return "full"

    def _collect_entries(
        self,
        *,
        conn: Any,
        source: IdentitySource,
        mode: str,
        capabilities: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        users: list[dict[str, Any]] = []
        groups: list[dict[str, Any]] = []
        memberships: list[dict[str, Any]] = []
        max_usn_changed: int | None = None
        dirsync_cookie: str | None = None

        base_dn = str(source.base_dn or "").strip()
        search_scope = LDAP_SCOPE_BY_NAME.get(str(capabilities.get("search_scope") or "subtree").strip().lower(), SUBTREE)
        page_size = max(100, min(int(capabilities.get("snapshot_page_size") or 1000), 2000))

        users_filter = self._build_delta_filter(
            base="(&(objectCategory=person)(objectClass=user)(!(objectClass=computer)))",
            mode=mode,
            source=source,
            field_usn="uSNChanged",
            field_when_changed="whenChanged",
        )
        groups_filter = self._build_delta_filter(
            base="(objectClass=group)",
            mode=mode,
            source=source,
            field_usn="uSNChanged",
            field_when_changed="whenChanged",
        )

        user_entries: list[Any] = []
        group_entries: list[Any] = []

        if mode == "dirsync":
            raw_cookie = str(source.last_dirsync_cookie or "").strip()
            cookie: bytes | None
            if raw_cookie:
                try:
                    cookie = bytes.fromhex(raw_cookie)
                except ValueError:
                    cookie = None
            else:
                cookie = None

            user_sync = conn.extend.microsoft.dir_sync(
                sync_base=base_dn,
                sync_filter=users_filter,
                attributes=USERS_ATTRS,
                cookie=cookie,
            )
            user_entries = list(user_sync.loop() or [])
            cookie = user_sync.cookie

            group_sync = conn.extend.microsoft.dir_sync(
                sync_base=base_dn,
                sync_filter=groups_filter,
                attributes=GROUPS_ATTRS,
                cookie=cookie,
            )
            group_entries = list(group_sync.loop() or [])
            dirsync_cookie = (group_sync.cookie or cookie or b"").hex() or None
        else:
            user_entries = list(
                conn.extend.standard.paged_search(
                    search_base=base_dn,
                    search_filter=users_filter,
                    search_scope=search_scope,
                    attributes=USERS_ATTRS,
                    paged_size=page_size,
                    generator=True,
                )
            )
            group_entries = list(
                conn.extend.standard.paged_search(
                    search_base=base_dn,
                    search_filter=groups_filter,
                    search_scope=search_scope,
                    attributes=GROUPS_ATTRS,
                    paged_size=page_size,
                    generator=True,
                )
            )

        user_external_ids: set[str] = set()

        for entry in group_entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") != "searchResEntry":
                continue
            attrs = entry.get("attributes") or {}
            dn = str(attrs.get("distinguishedName") or entry.get("dn") or "").strip()
            if not dn:
                continue

            object_guid = _to_guid(attrs.get("objectGUID"))
            object_sid = _to_sid(attrs.get("objectSid"))
            name = str(attrs.get("cn") or attrs.get("sAMAccountName") or dn).strip()
            code = str(attrs.get("sAMAccountName") or attrs.get("cn") or "").strip() or None
            when_changed = _to_datetime(attrs.get("whenChanged"))
            usn_changed = _to_int(attrs.get("uSNChanged"))
            if usn_changed is not None:
                max_usn_changed = max(max_usn_changed or usn_changed, usn_changed)

            external_id = dn
            groups.append(
                {
                    "external_id": external_id,
                    "dn": dn,
                    "name": name,
                    "code": code,
                    "description": None,
                    "when_changed": when_changed,
                    "usn_changed": usn_changed,
                    "is_active": True,
                }
            )

            members_raw = attrs.get("member")
            members = members_raw if isinstance(members_raw, list) else ([members_raw] if members_raw else [])
            for member_dn in members:
                member_dn = str(member_dn or "").strip()
                if not member_dn:
                    continue
                memberships.append(
                    {
                        "group_external_id": external_id,
                        "member_external_id": member_dn,
                        "member_type": "user",  # resolved after user/group map is built
                    }
                )

        for entry in user_entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") != "searchResEntry":
                continue
            attrs = entry.get("attributes") or {}
            dn = str(attrs.get("distinguishedName") or entry.get("dn") or "").strip()
            if not dn:
                continue

            object_guid = _to_guid(attrs.get("objectGUID"))
            object_sid = _to_sid(attrs.get("objectSid"))
            external_id = dn
            user_external_ids.add(external_id.lower())
            user_external_ids.add(dn.lower())

            username = str(attrs.get("sAMAccountName") or attrs.get("userPrincipalName") or attrs.get("cn") or dn).strip()
            display_name = str(attrs.get("cn") or username or external_id).strip()
            email = str(attrs.get("mail") or "").strip() or None
            upn = str(attrs.get("userPrincipalName") or "").strip() or None
            when_changed = _to_datetime(attrs.get("whenChanged"))
            usn_changed = _to_int(attrs.get("uSNChanged"))
            if usn_changed is not None:
                max_usn_changed = max(max_usn_changed or usn_changed, usn_changed)

            users.append(
                {
                    "external_id": external_id,
                    "object_guid": object_guid,
                    "object_sid": object_sid,
                    "upn": upn,
                    "dn": dn,
                    "username": username,
                    "display_name": display_name,
                    "email": email,
                    "when_changed": when_changed,
                    "usn_changed": usn_changed,
                    "source": "ad_snapshot",
                    "is_active": _ad_user_enabled(attrs),
                }
            )

        # Resolve membership type user/group with the group list discovered above
        normalized_group_ids = {g["external_id"].lower() for g in groups if str(g.get("external_id") or "").strip()}
        normalized_group_dns = {
            str(g.get("dn") or "").strip().lower()
            for g in groups
            if str(g.get("dn") or "").strip()
        }
        for item in memberships:
            member_external = str(item.get("member_external_id") or "").strip().lower()
            if member_external in normalized_group_ids or member_external in normalized_group_dns:
                item["member_type"] = "group"
            elif member_external in user_external_ids:
                item["member_type"] = "user"
            else:
                # keep default 'user' to preserve backward compatibility
                item["member_type"] = "user"

        return users, groups, memberships, {
            "max_usn_changed": max_usn_changed,
            "dirsync_cookie": dirsync_cookie,
        }

    def _build_delta_filter(
        self,
        *,
        base: str,
        mode: str,
        source: IdentitySource,
        field_usn: str,
        field_when_changed: str,
    ) -> str:
        if mode == "usn" and source.last_usn_changed is not None:
            return f"(&{base}({field_usn}>={int(source.last_usn_changed)}))"

        if mode == "whenchanged" and source.last_snapshot_at is not None:
            stamp = source.last_snapshot_at.strftime("%Y%m%d%H%M%S.0Z")
            return f"(&{base}({field_when_changed}>={stamp}))"

        return base

    def _update_source_snapshot_metadata(
        self,
        *,
        source: IdentitySource,
        snapshot_id: int,
        snapshot_version: int | None,
        mode: str,
        max_usn_changed: int | None,
        dirsync_cookie: str | None,
    ) -> None:
        source.last_snapshot_at = dt.datetime.utcnow()
        source.last_snapshot_version = snapshot_version
        if max_usn_changed is not None:
            source.last_usn_changed = int(max_usn_changed)
        if dirsync_cookie:
            source.last_dirsync_cookie = dirsync_cookie
            source.dirsync_supported = True
        source.snapshot_mode = mode
        source.delta_supported = mode in {"dirsync", "usn", "whenchanged"}

        # Keep capabilities synced (best effort, backward compatible)
        caps = dict(source.capabilities or {})
        caps["snapshot_mode"] = mode
        caps["delta_supported"] = bool(source.delta_supported)
        caps["dirsync_supported"] = bool(source.dirsync_supported)
        source.capabilities = caps

        self.db.add(source)
        self.db.commit()
