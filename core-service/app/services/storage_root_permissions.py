"""Permissions of a storage root, as people see them (Storage roots › Permissions).

Three sources, read together:
  - the NTFS ACL of the folder, as last read on the file server (storage_roots.discovered_permissions_json)
  - the AD groups BornToShare manages for the root (storage_root_access_profiles) and their members in the
    active directory snapshot
  - the access requests in force (approved, neither revoked nor expired), for their BENEFICIARY

The ACL entries are sorted into: groups managed by BornToShare, system and administration accounts, and gaps
(anything else, unless accepted). People get one row each, with the highest level and every way they get it.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.storage_root_access_profile_resolution import normalize_requested_permission

# Accounts expected on every governed folder (beside the endpoint service account)
# (English and French Windows: the names read in an ACL follow the language of the server)
_SYSTEM_NAMESPACES = {"NT AUTHORITY", "AUTORITE NT", "AUTORITÉ NT", "BUILTIN"}
_SYSTEM_NAMES = {
    "system", "système", "systeme", "administrators", "administrateurs", "domain admins", "admins du domaine",
    "enterprise admins", "administrateurs de l'entreprise", "administrateurs de l’entreprise", "administrator",
    "administrateur", "creator owner", "createur proprietaire", "créateur propriétaire",
}
# Everyone-like principals are never « system »: they open the folder widely
_BROAD_NAMES = {
    "everyone", "tout le monde", "authenticated users", "utilisateurs authentifiés", "utilisateurs authentifies",
    "domain users", "utilisateurs du domaine", "users", "utilisateurs",
}

_RIGHTS_LABELS = {"full": "Full control", "modify": "Modify", "read": "Read and execute", "special": "Special", "deny": "Denied"}
_GROUP_STATUSES = ("SUCCEEDED", "ADOPTING")


def inheritance_state(control: Any, aces: list[dict[str, Any]]) -> dict[str, Any]:
    """NTFS inheritance of the folder: PD in the CONTROL flags = broken; the I flag marks an entry from the parent."""
    flags = [f.strip().upper() for f in str(control or "").split("|") if f.strip()]
    inherited = 0
    for ace in aces:
        parts = str(ace.get("raw") or "").upper().split("/")
        if len(parts) > 2 and "I" in parts[1].split("|"):
            inherited += 1
    return {"known": bool(flags), "broken": "PD" in flags, "inherited_entries": inherited}


def is_expected_system_principal(principal: str | None, service_account: str | None = None) -> bool:
    """SYSTEM, BUILTIN, domain administrators and the file server account of BornToShare: expected on every folder."""
    raw = str(principal or "").replace("/", "\\")
    namespace = raw.split("\\")[0].upper() if "\\" in raw else ""
    name = short_name(raw)
    if name in _BROAD_NAMES:
        return False
    return namespace in _SYSTEM_NAMESPACES or name in _SYSTEM_NAMES or bool(service_account and name == account_name(service_account))


def is_broad_principal(principal: str | None) -> bool:
    """Everyone, Users, Domain users…: the folder is open to the whole company, whatever the requests say."""
    return short_name(principal) in _BROAD_NAMES


def account_name(account: str | None) -> str:
    """Login of an account written DOMAIN\\login, login@domain or CN=login,OU=…"""
    raw = str(account or "").strip()
    if raw.lower().startswith("cn="):
        raw = raw[3:].split(",", 1)[0]
    return short_name(raw.split("@", 1)[0])


def short_name(principal: str | None) -> str:
    """DOMAIN\\name -> name (lower case)."""
    raw = str(principal or "").strip().replace("/", "\\")
    return raw.split("\\")[-1].strip().lower()


def rights_from_raw(raw: str | None) -> str:
    """smbcacls rights (ALLOWED/OI|CI/READ, .../RWXD, .../FULL, hex masks) -> full | modify | read | special | deny."""
    value = str(raw or "").strip().upper()
    if value.startswith("DENIED"):
        return "deny"
    mask = value.split("/")[-1].strip()
    if mask in {"FULL", "0X001F01FF"} or "FULL" in mask:
        return "full"
    if mask in {"RWXD", "CHANGE", "0X001301BF", "0X1301BF"}:
        return "modify"
    if mask in {"READ", "R", "RX", "0X001200A9", "0X1200A9", "0X00120089", "0X120089"}:
        return "read"
    return "special"


def level_from_rights(rights: str) -> str | None:
    return {"full": "write", "modify": "write", "read": "read"}.get(rights)


def inherited_scope(raw: str | None) -> bool:
    """OI|CI: applies to this folder, its subfolders and files."""
    flags = str(raw or "").upper()
    return "OI" in flags and "CI" in flags


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat()
    return str(value)


class StorageRootPermissions:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _all(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute(text(sql), params).mappings().all()]

    def _one(self, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
        row = self.db.execute(text(sql), params).mappings().first()
        return dict(row) if row else None

    # ------------------------------------------------------------------ inputs

    def _root(self, root_id: int) -> dict[str, Any] | None:
        return self._one(
            """
            SELECT sr.id, sr.name, sr.root_path, sr.discovered_permissions_json, sr.storage_endpoint_id,
                   se.identity_source_id, se.bind_dn AS endpoint_account, se.name AS endpoint_name
            FROM storage_roots sr
            JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            WHERE sr.id = :id
            """,
            {"id": int(root_id)},
        )

    def group_members(self, group_name: str, source_id: int | None) -> list[dict[str, Any]]:
        """Direct and nested members of an AD group in the active snapshot (every user, known to BornToShare or not)."""
        if not source_id:
            return []
        return self._all(
            """
            SELECT DISTINCT du.username, du.display_name, du.upn, du.dn, du.email, MIN(dem.depth) AS depth
            FROM directory_groups dg
            JOIN directory_effective_memberships dem
              ON dem.directory_group_id = dg.id AND dem.identity_source_id = dg.identity_source_id
            JOIN directory_users du ON du.id = dem.directory_user_id
            LEFT JOIN directory_snapshots ds ON ds.id = dem.snapshot_id
            WHERE dg.deleted_at IS NULL
              AND dg.identity_source_id = :source
              AND (LOWER(dg.name) = LOWER(:name) OR LOWER(COALESCE(dg.code, '')) = LOWER(:name))
              AND (dem.snapshot_id IS NULL OR UPPER(COALESCE(ds.status, '')) = 'ACTIVE')
            GROUP BY du.username, du.display_name, du.upn, du.dn, du.email
            ORDER BY LOWER(COALESCE(du.display_name, du.username))
            """,
            {"source": int(source_id), "name": group_name},
        )

    def _group_info(self, group_name: str, source_id: int | None) -> dict[str, Any] | None:
        if not source_id:
            return None
        return self._one(
            """
            SELECT dn, name FROM directory_groups
            WHERE identity_source_id = :source AND deleted_at IS NULL
              AND (LOWER(name) = LOWER(:name) OR LOWER(COALESCE(code, '')) = LOWER(:name))
            LIMIT 1
            """,
            {"source": int(source_id), "name": group_name},
        )

    def _snapshot_at(self, source_id: int | None) -> str | None:
        if not source_id:
            return None
        return _iso(
            self.db.execute(
                text("SELECT last_snapshot_at FROM identity_sources WHERE id = :id"), {"id": int(source_id)}
            ).scalar()
        )

    def _requests(self, root_id: int) -> list[dict[str, Any]]:
        rows = self._all(
            """
            SELECT ar.id, ar.code, ar.decided_at, ar.requested_principal_json, ari.permission, ari.expires_at,
                   COALESCE(i.display_name, i.username) AS requester
            FROM access_requests ar
            JOIN access_request_items ari ON ari.access_request_id = ar.id
            LEFT JOIN identities i ON i.id = ar.requester_identity_id
            WHERE LOWER(COALESCE(ari.target_type, '')) = 'storage_root' AND ari.target_id = :id
              AND LOWER(COALESCE(ar.status, '')) IN ('approved', 'executed')
              AND ar.revoked_at IS NULL
              AND (ari.expires_at IS NULL OR ari.expires_at > UTC_TIMESTAMP())
            ORDER BY ar.decided_at DESC
            """,
            {"id": int(root_id)},
        )
        for row in rows:
            row["principal"] = _json(row.pop("requested_principal_json"))
            row["level"] = (normalize_requested_permission(str(row.get("permission") or "")) or "READ").lower()
        return rows

    def _exceptions(self, root_id: int) -> dict[str, dict[str, Any]]:
        try:
            rows = self._all(
                "SELECT principal, note, accepted_by, accepted_at FROM storage_root_acl_exceptions WHERE storage_root_id = :id",
                {"id": int(root_id)},
            )
        except Exception:  # table not migrated yet: nothing accepted
            self.db.rollback()
            return {}
        return {str(r["principal"]).lower(): r for r in rows}

    # ------------------------------------------------------------------ result

    def _propagation(self, root_id: int) -> dict[str, Any] | None:
        """Latest background propagation of the ACL to the content of the folder."""
        rows = self._all(
            """
            SELECT status, error_message, finished_at
            FROM provisioning_jobs
            WHERE job_type = 'ACL_APPLY'
              AND created_at > UTC_TIMESTAMP() - INTERVAL 30 DAY
              AND JSON_VALUE(payload_json, '$.payload.context.acl_propagation') IN ('true', '1')
              AND JSON_VALUE(payload_json, '$.payload.context.storage_root_id') = :root_id
            ORDER BY id DESC
            LIMIT 4
            """,
            {"root_id": str(int(root_id))},
        )
        if not rows:
            return None
        statuses = [str(r.get("status") or "").upper() for r in rows]
        if any(s in {"QUEUED", "PENDING", "RUNNING", "RETRYING"} for s in statuses):
            return {"state": "running"}
        if statuses[0] in {"FAILED", "TIMED_OUT", "CANCELLED"}:
            return {"state": "failed", "message": rows[0].get("error_message")}
        return {"state": "done", "at": _iso(rows[0].get("finished_at"))}

    def build(self, root_id: int) -> dict[str, Any] | None:
        root = self._root(root_id)
        if root is None:
            return None
        source_id = int(root.get("identity_source_id") or 0) or None
        scan = _json(root.get("discovered_permissions_json"))
        aces = [dict(a) for a in (scan.get("permissions") or []) if isinstance(a, dict) and a.get("principal")]
        scanned_at = scan.get("discovered_at")
        exceptions = self._exceptions(root_id)
        service_account = account_name(root.get("endpoint_account"))

        profiles = self._all(
            """
            SELECT id, access_level_code, group_name, group_external_id, status
            FROM storage_root_access_profiles WHERE storage_root_id = :id ORDER BY access_level_code
            """,
            {"id": int(root_id)},
        )
        profile_by_name = {short_name(p["group_name"]): p for p in profiles if p.get("group_name")}

        managed_aces: dict[str, dict[str, Any]] = {}
        system: list[dict[str, Any]] = []
        gaps: list[dict[str, Any]] = []
        for ace in aces:
            principal = str(ace["principal"]).strip()
            name = short_name(principal)
            raw = str(ace.get("raw") or "")
            rights = rights_from_raw(raw)
            entry = {
                "principal": principal,
                "name": principal.replace("/", "\\").split("\\")[-1],
                "rights": rights,
                "rights_label": _RIGHTS_LABELS[rights],
                "level": level_from_rights(rights),
                "inherited_scope": inherited_scope(raw),
                "raw": raw,
            }
            namespace = principal.replace("/", "\\").split("\\")[0].upper() if "\\" in principal.replace("/", "\\") else ""
            if name in profile_by_name:
                managed_aces[name] = entry
            elif name in _BROAD_NAMES:
                gaps.append({**entry, "kind": "broad"})
            elif namespace in _SYSTEM_NAMESPACES or name in _SYSTEM_NAMES or (service_account and name == service_account):
                system.append({**entry, "kind": "service" if name == service_account else "system"})
            else:
                gaps.append({**entry, "kind": "outside"})

        # Groups managed by BornToShare, with their ACE and their members
        groups: list[dict[str, Any]] = []
        members_by_group: dict[str, list[dict[str, Any]]] = {}
        for profile in profiles:
            if str(profile.get("status") or "").upper() not in _GROUP_STATUSES:
                continue
            name = str(profile["group_name"])
            level = "write" if str(profile["access_level_code"]).upper() == "WRITE" else "read"
            ace = managed_aces.get(short_name(name))
            expected = {"read": {"read"}, "write": {"modify", "full"}}[level]
            ace_state = "missing" if ace is None else ("ok" if ace["rights"] in expected else "mismatch")
            members = self.group_members(name, source_id)
            members_by_group[name] = members
            info = self._group_info(name, source_id) or {}
            groups.append({
                "name": name,
                "level": level,
                "dn": info.get("dn") or (profile.get("group_external_id") if "=" in str(profile.get("group_external_id") or "") else None),
                "ace": ace_state if scanned_at else "unknown",
                "rights_label": ace["rights_label"] if ace else None,
                "inherited_scope": bool(ace and ace["inherited_scope"]),
                "members_count": len(members),
            })

        # Gaps: accepted or not; a group in a gap gives access to its members
        for gap in gaps:
            accepted = exceptions.get(gap["principal"].lower())
            gap["accepted"] = bool(accepted)
            gap["accepted_by"] = (accepted or {}).get("accepted_by")
            gap["members"] = self.group_members(gap["name"], source_id) if gap["kind"] == "outside" else []
            gap["members_count"] = len(gap["members"])

        # People: one row per person, every way they get access, the highest level
        people: dict[str, dict[str, Any]] = {}

        def person(key_source: dict[str, Any]) -> dict[str, Any]:
            username = str(key_source.get("username") or "").strip()
            key = (username or str(key_source.get("dn") or key_source.get("display_name") or "")).lower()
            row = people.get(key)
            if row is None:
                row = people[key] = {
                    "key": key,
                    "username": username or None,
                    "name": key_source.get("display_name") or username or key_source.get("dn"),
                    "dn": key_source.get("dn"),
                    "level": None,
                    "via": [],
                    "expires_at": None,
                    "revocable_request_ids": [],
                    "warnings": [],
                }
            return row

        def raise_level(row: dict[str, Any], level: str | None) -> None:
            if level == "write" or (level == "read" and row["level"] is None):
                row["level"] = level

        requests = self._requests(root_id)
        request_keys: dict[str, list[dict[str, Any]]] = {}
        for req in requests:
            principal = req["principal"]
            if str(principal.get("type") or "user").lower() != "user":
                continue
            row = person(principal)
            raise_level(row, req["level"])
            row["via"].append({
                "kind": "request",
                "request_id": int(req["id"]),
                "code": req.get("code") or f"REQ-{req['id']}",
                "level": req["level"],
                "group": next((g["name"] for g in groups if g["level"] == req["level"]), None),
                "decided_at": _iso(req.get("decided_at")),
                "expires_at": _iso(req.get("expires_at")),
                "requester": req.get("requester"),
            })
            row["revocable_request_ids"].append(int(req["id"]))
            request_keys.setdefault(row["key"], []).append(req)

        for group in groups:
            for member in members_by_group.get(group["name"], []):
                row = person(member)
                raise_level(row, group["level"])
                covered = any(r["level"] == group["level"] for r in request_keys.get(row["key"], []))
                row["via"].append({"kind": "group" if covered else "ad_only", "group": group["name"], "level": group["level"],
                                   "nested": int(member.get("depth") or 0) > 0})

        for gap in gaps:
            for member in gap["members"]:
                row = person(member)
                raise_level(row, gap["level"])
                row["via"].append({"kind": "outside", "group": gap["name"], "level": gap["level"], "accepted": gap["accepted"]})

        snapshot_at = self._snapshot_at(source_id)
        for row in people.values():
            # The expiry shown is the one of the request that gives the level kept
            expiring = [v["expires_at"] for v in row["via"] if v["kind"] == "request" and v["level"] == row["level"]]
            row["expires_at"] = None if not expiring or any(e is None for e in expiring) else max(expiring)
            # Approved but not yet seen in the AD group: the next directory sync confirms it
            for via in row["via"]:
                if via["kind"] == "request" and via.get("group") and not any(
                    v["kind"] in {"group", "ad_only"} and v["group"] == via["group"] for v in row["via"]
                ):
                    newer = snapshot_at and via.get("decided_at") and snapshot_at > via["decided_at"]
                    row["warnings"].append("missing_in_group" if newer else "awaiting_sync")
            row["via"].sort(key=lambda v: {"request": 0, "group": 1, "ad_only": 2, "outside": 3}[v["kind"]])

        people_rows = sorted(people.values(), key=lambda r: (r["level"] != "write", str(r["name"] or "").lower()))
        horizon = (datetime.now(timezone.utc) + timedelta(days=30)).replace(tzinfo=None).isoformat()
        open_gaps = [g for g in gaps if not g["accepted"]]
        missing = [g for g in groups if g["ace"] in {"missing", "mismatch"}]
        status = "never_scanned" if not scanned_at else "missing_ace" if missing else "gap" if open_gaps else "ok"

        for gap in gaps:
            gap.pop("members", None)
        propagation = self._propagation(root_id)
        if status == "ok" and propagation and propagation["state"] == "running":
            # Compliant on the folder, not yet on all its content
            status = "applying"
        elif status == "ok" and propagation and propagation["state"] == "failed":
            # The rights did not reach everything: never « compliant », the banner of the tab says why
            status = "missing_ace"
        return {
            "storage_root_id": int(root_id),
            "root_path": root.get("root_path"),
            "acl_scanned_at": scanned_at,
            "acl_entries": len(aces),
            "inheritance": inheritance_state(scan.get("control"), aces),
            "propagation": propagation,
            "snapshot_at": snapshot_at,
            "status": status,
            "summary": {
                "people": len(people_rows),
                "read": sum(1 for p in people_rows if p["level"] == "read"),
                "write": sum(1 for p in people_rows if p["level"] == "write"),
                "groups": len(groups),
                "groups_ok": sum(1 for g in groups if g["ace"] == "ok"),
                "expiring_30d": sum(1 for p in people_rows if p["expires_at"] and p["expires_at"] <= horizon),
                "gaps": len(open_gaps),
                "accepted_gaps": len(gaps) - len(open_gaps),
            },
            "people": people_rows,
            "groups": groups,
            "system": system,
            "gaps": gaps,
        }

    def search_people(self, query: str, limit: int = 6) -> list[dict[str, Any]]:
        """Directory users matching a login or a name, with the storage roots they reach (⌘K palette)."""
        like = f"%{query.strip().lower()}%"
        rows = self._all(
            """
            SELECT du.username, MAX(du.display_name) AS display_name, MAX(du.dn) AS dn,
                   MAX(du.identity_source_id) AS identity_source_id
            FROM directory_users du
            WHERE du.username IS NULL OR du.username <> ''
            GROUP BY du.username
            HAVING LOWER(du.username) LIKE :q OR LOWER(COALESCE(MAX(du.display_name), '')) LIKE :q
            ORDER BY du.username
            LIMIT :limit
            """,
            {"q": like, "limit": int(limit)},
        )
        return [
            {"username": r["username"], "name": r["display_name"] or r["username"], "dn": r["dn"],
             "identity_source_id": r["identity_source_id"], "roots": self.other_roots(str(r["username"]), 0)}
            for r in rows if r.get("username")
        ]

    def other_roots(self, username: str, exclude_root_id: int) -> list[dict[str, Any]]:
        """Other storage roots a person reaches through BornToShare (requests in force or managed groups)."""
        rows = self._all(
            """
            SELECT sr.id, sr.name, srap.access_level_code AS level
            FROM directory_users du
            JOIN directory_effective_memberships dem ON dem.directory_user_id = du.id
            JOIN directory_groups dg ON dg.id = dem.directory_group_id AND dg.deleted_at IS NULL
            LEFT JOIN directory_snapshots ds ON ds.id = dem.snapshot_id
            JOIN storage_root_access_profiles srap ON LOWER(srap.group_name) = LOWER(dg.name)
            JOIN storage_roots sr ON sr.id = srap.storage_root_id
            WHERE LOWER(du.username) = LOWER(:username) AND sr.id <> :root
              AND (dem.snapshot_id IS NULL OR UPPER(COALESCE(ds.status, '')) = 'ACTIVE')
            """,
            {"username": username, "root": int(exclude_root_id)},
        )
        best: dict[int, dict[str, Any]] = {}
        for row in rows:
            level = "write" if str(row["level"]).upper() == "WRITE" else "read"
            current = best.get(int(row["id"]))
            if current is None or level == "write":
                best[int(row["id"])] = {"storage_root_id": int(row["id"]), "name": row["name"], "level": level}
        return sorted(best.values(), key=lambda r: str(r["name"]).lower())
