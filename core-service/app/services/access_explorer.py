"""Access Explorer: who reaches what, and why, from what BornToShare already reads.

Sources (nothing is read from the servers here):
- the NTFS entries of the last ACL read of each governed folder, indexed by account name (storage_root_acl_entries,
  schema/166_access_explorer.sql, kept in step by services/root_payload.py);
- the active directory snapshot of the folder's identity source: users (account state when it was read), groups,
  and the memberships, group in group included (directory_snapshot_memberships).

What is known is said, what is not is listed in « limits »: the share permissions (SMB) are not read, the network
rules neither, the local groups of the server are not resolved, a sub-folder may break the inheritance. An effective
access is therefore never claimed complete: the NTFS rights are « at most » what the account gets.

Performance: every lookup is targeted (the entries of the account's own groups, the entries of one folder), the
folder lists are paged by the server, the group walk stops at MAX_DEPTH and never loops, and the walks are cached per
directory snapshot (a new snapshot is a new key: nothing stale is served).
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable, Iterable

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.services.authorization import get_guardian_storage_root_ids, is_platform_administrator
from app.services.storage_root_permissions import (
    _BROAD_NAMES,
    _extra_broad_names,
    _json,
    is_expected_system_principal,
    rights_from_raw,
    short_name,
)

MAX_DEPTH = 10
PAGE_MAX = 200
PEOPLE_ROWS_MAX = 20000
_RANK = {"read": 1, "special": 1, "modify": 2, "full": 3}

# Limits of the computation, translated by the page
LIMIT_NTFS_ONLY = "ntfs_only"  # share permissions (SMB) and network rules not read
LIMIT_SUBFOLDERS = "subfolders_not_read"  # rights read on the governed folder only
LIMIT_LOCAL_GROUPS = "local_groups_not_resolved"  # BUILTIN\Administrators… of the server
LIMIT_DENY = "deny_present"  # a deny entry: the effective right may be lower
LIMIT_ACCOUNT_STATE = "account_state_unknown"  # the reading did not carry the account state
LIMIT_NO_SNAPSHOT = "no_directory_snapshot"
LIMIT_DEPTH = "group_depth_truncated"
LIMIT_ACL_NOT_READ = "acl_not_read"
LIMIT_PEOPLE_TRUNCATED = "people_truncated"


# ---------------------------------------------------------------- pure computation (tested without a database)


def ace_info(principal: str, raw: str | None) -> dict[str, Any]:
    """One NTFS entry: rights (full, modify, read, special), deny, inherited (I flag: comes from a parent folder)."""
    value = str(raw or "")
    rights = rights_from_raw(value)
    parts = value.split("/")
    flags = parts[1].upper().split("|") if len(parts) >= 3 else []
    deny = rights == "deny"
    if deny:
        # The denied rights, read from the mask as for an allow
        rights = rights_from_raw("ALLOWED/" + "/".join(parts[1:])) if len(parts) >= 3 else "special"
    return {"principal": principal, "rights": rights, "deny": deny, "inherited": "I" in flags, "raw": value}


def walk(edges: Callable[[set[str]], Iterable[tuple[str, str]]], start: str, max_depth: int = MAX_DEPTH) -> dict[str, Any]:
    """Breadth-first walk of the membership graph from `start`. edges(frontier) yields (next, came_from) pairs: the
    groups holding a member (upwards) or the members of a group (downwards). Each node keeps its shortest path
    (start excluded) and its depth (0 = directly linked). A node already seen is never walked again: a loop of groups
    (A in B in A) ends. truncated: nodes remained beyond max_depth."""
    seen: dict[str, dict[str, Any]] = {}
    paths: dict[str, list[str]] = {start: []}
    frontier = {start}
    depth = 0
    truncated = False
    while frontier:
        if depth > max_depth:
            truncated = True
            break
        nxt: set[str] = set()
        for node, came_from in edges(frontier):
            if node == start or node in seen:
                continue
            path = [*paths.get(came_from, []), node]
            seen[node] = {"depth": depth, "path": path}
            paths[node] = path
            nxt.add(node)
        frontier = nxt
        depth += 1
    return {"nodes": seen, "truncated": truncated}


def summarize(grants: list[dict[str, Any]]) -> dict[str, Any]:
    """What the entries of one folder give: the strongest allowed NTFS right, whether a deny is there, how many ways."""
    allowed = [g for g in grants if not g["deny"]]
    best = max((g["rights"] for g in allowed), key=lambda r: _RANK.get(r, 0), default=None)
    return {
        "ntfs_rights": best,
        "denied": any(g["deny"] for g in grants),
        "paths": len(grants),
        "multiple_paths": len(grants) > 1,
        "inherited_only": bool(grants) and all(g["inherited"] for g in grants),
    }


def principal_kind(principal: str, *, broad: bool, service_account: str | None, group: bool, user: bool) -> str:
    """broad (whole company), system (expected accounts), orphan (SID without name), group, user, unknown."""
    if broad:
        return "broad"
    if str(principal).upper().startswith("S-1-"):
        return "orphan"
    if is_expected_system_principal(principal, service_account):
        return "system"
    if group:
        return "group"
    if user:
        return "user"
    return "unknown"


def merge_people(direct: list[dict[str, Any]], via_groups: list[dict[str, Any]], grants_by_key: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per person of a folder: each way they get in (their account, a group directly or nested), the strongest
    right, a deny if any. direct: users with an entry of their own; via_groups: (user, group key, depth) rows."""
    people: dict[int, dict[str, Any]] = {}

    def row(user: dict[str, Any]) -> dict[str, Any]:
        uid = int(user["user_id"])
        return people.setdefault(uid, {"user_id": uid, "username": user.get("username"), "display_name": user.get("display_name"),
                                       "is_active": user.get("is_active"), "grants": []})

    for user in direct:
        grant = grants_by_key.get(user["key"])
        if grant:
            row(user)["grants"].append({**grant, "kind": "direct"})
    for member in via_groups:
        grant = grants_by_key.get(member["key"])
        if grant:
            kind = "nested" if int(member.get("depth") or 0) > 0 else "group"
            row(member)["grants"].append({**grant, "kind": kind, "group": member.get("group_name"), "depth": int(member.get("depth") or 0)})
    out = []
    for person in people.values():
        out.append({**person, **summarize(person["grants"])})
    out.sort(key=lambda p: (-_RANK.get(p["ntfs_rights"] or "", 0), str(p["display_name"] or p["username"] or "").lower()))
    return out


def folders_from_entries(rows: list[dict[str, Any]], origins: dict[str, list[dict[str, Any]]], order: list[int]) -> list[dict[str, Any]]:
    """The folders of a page from their matching ACL entries: each entry, once per way the account gets its name (an
    account in two groups named on one folder has two grants: « several paths »), then what they give together."""
    by_root: dict[int, dict[str, Any]] = {}
    for row in rows:
        rid = int(row["storage_root_id"])
        scan = _json(row.get("discovered_permissions_json"))
        folder = by_root.setdefault(rid, {"storage_root_id": rid, "name": row.get("name"), "root_path": row.get("root_path"),
                                          "endpoint_name": row.get("endpoint_name"), "acl_read_at": scan.get("discovered_at"),
                                          "inheritance_broken": "PD" in str(scan.get("control") or "").upper().split("|"),
                                          "grants": []})
        ace = ace_info(str(row["principal"]), row.get("raw"))
        local = namespace(str(row["principal"])) in LOCAL_NAMESPACES
        for origin in origins.get(str(row["principal_key"]).lower(), []):
            if local and origin["kind"] != "broad":
                continue
            folder["grants"].append({**ace, **origin})
    items = []
    for rid in order:
        folder = by_root.get(rid)
        if folder:
            folder["grants"].sort(key=lambda g: (_KIND_ORDER.get(g["kind"], 4), g["deny"]))
            items.append({**folder, **summarize(folder["grants"])})
    return items


LOCAL_NAMESPACES = {"BUILTIN", "NT AUTHORITY", "AUTORITE NT", "AUTORITÉ NT"}
_NAMESPACE_SQL = r"UPPER(SUBSTRING_INDEX(REPLACE(e.principal, '/', '\\'), '\\', 1))"


def namespace(principal: str) -> str:
    """CORP\\GG_X → CORP; a name without domain (Everyone) has none."""
    value = str(principal or "").strip().replace("/", "\\")
    return value.split("\\", 1)[0].strip().upper() if "\\" in value else ""


_KIND_ORDER = {"direct": 0, "group": 1, "nested": 2, "parent": 2, "broad": 3}


def account_state(is_active: Any, state_read: bool) -> str:
    """enabled / disabled when the reading carried the account state, unknown otherwise (never a guessed « enabled »);
    not_in_directory: the account is not in the last reading."""
    if is_active is None:
        return "not_in_directory" if state_read else "unknown"
    if not state_read:
        return "unknown"
    return "enabled" if int(is_active) else "disabled"


def broad_keys() -> set[str]:
    return set(_BROAD_NAMES) | set(_extra_broad_names())


# ---------------------------------------------------------------- inputs


class _Cache:
    """Walks per (snapshot, direction, start): a new directory snapshot is a new key, so nothing stale is served."""

    def __init__(self, size: int = 512) -> None:
        self.size = size
        self.items: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()

    def get(self, key: tuple[Any, ...], build: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        if key in self.items:
            self.items.move_to_end(key)
            return self.items[key]
        value = build()
        self.items[key] = value
        while len(self.items) > self.size:
            self.items.popitem(last=False)
        return value


_WALKS = _Cache()


def _page(offset: int | None, limit: int | None, default: int = 50) -> tuple[int, int]:
    return max(0, int(offset or 0)), max(1, min(int(limit or default), PAGE_MAX))


class AccessExplorer:
    def __init__(self, db: Session, actor: Any) -> None:
        self.db = db
        self.actor = actor
        self.admin = is_platform_administrator(actor)
        self._allowed: set[int] | None = None if self.admin else set(get_guardian_storage_root_ids(db, actor))

    # ------------------------------------------------------------ helpers

    def _all(self, sql: str, params: dict[str, Any] | None = None, expanding: Iterable[str] = ()) -> list[dict[str, Any]]:
        statement = text(sql)
        for name in expanding:
            statement = statement.bindparams(bindparam(name, expanding=True))
        return [dict(r) for r in self.db.execute(statement, params or {}).mappings().all()]

    def _one(self, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        row = self.db.execute(text(sql), params or {}).mappings().first()
        return dict(row) if row else None

    def _scope(self, column: str = "sr.id") -> tuple[str, dict[str, Any], list[str]]:
        """The folders of a guardian only; everything for an administrator."""
        if self._allowed is None:
            return "", {}, []
        return f" AND {column} IN :allowed", {"allowed": sorted(self._allowed) or [0]}, ["allowed"]

    def can_see_root(self, root_id: int) -> bool:
        return self._allowed is None or int(root_id) in self._allowed

    def _snapshot(self, source_id: int | None) -> dict[str, Any] | None:
        if not source_id:
            return None
        row = self._one(
            """SELECT id, activated_at, completed_at, summary_json FROM directory_snapshots
               WHERE identity_source_id = :s AND UPPER(status) = 'ACTIVE' ORDER BY id DESC LIMIT 1""",
            {"s": int(source_id)},
        )
        if row is None:
            return None
        summary = _json(row.get("summary_json"))
        return {"id": int(row["id"]), "at": _iso(row.get("activated_at") or row.get("completed_at")),
                "account_state_read": bool(summary.get("account_state_read"))}

    def _walk(self, snapshot_id: int, start: str, direction: str) -> dict[str, Any]:
        """Groups holding `start` (up) or groups inside the group `start` (down), from the active snapshot."""
        if direction == "up":
            sql = """SELECT group_external_id AS node, member_external_id AS came_from FROM directory_snapshot_memberships
                     WHERE snapshot_id = :s AND member_external_id IN :frontier"""
        else:
            sql = """SELECT member_external_id AS node, group_external_id AS came_from FROM directory_snapshot_memberships
                     WHERE snapshot_id = :s AND member_type = 'group' AND group_external_id IN :frontier"""

        def edges(frontier: set[str]) -> list[tuple[str, str]]:
            rows = self._all(sql, {"s": snapshot_id, "frontier": sorted(frontier)}, ["frontier"])
            return [(str(r["node"]), str(r["came_from"])) for r in rows]

        return _WALKS.get((snapshot_id, direction, start), lambda: walk(edges, start))

    def _groups_by_external(self, snapshot_id: int, source_id: int, externals: Iterable[str]) -> dict[str, dict[str, Any]]:
        ids = sorted(set(externals))
        if not ids:
            return {}
        rows = self._all(
            """SELECT sg.external_id, sg.name, sg.code, sg.dn, dg.id AS group_id
               FROM directory_snapshot_groups sg
               LEFT JOIN directory_groups dg ON dg.identity_source_id = :src AND dg.external_id = sg.external_id AND dg.deleted_at IS NULL
               WHERE sg.snapshot_id = :s AND sg.external_id IN :ids""",
            {"s": snapshot_id, "src": source_id, "ids": ids}, ["ids"],
        )
        return {str(r["external_id"]): r for r in rows}

    # ------------------------------------------------------------ search (autocomplete, paged)

    def search(self, mode: str, q: str, offset: int | None = None, limit: int | None = None) -> dict[str, Any]:
        offset, limit = _page(offset, limit, 20)
        term = f"%{str(q or '').strip()}%"
        params = {"q": term, "limit": limit, "offset": offset}
        if mode == "user":
            where = """FROM directory_users du JOIN identity_sources s ON s.id = du.identity_source_id
                       WHERE (du.username LIKE :q OR du.display_name LIKE :q OR du.upn LIKE :q OR du.email LIKE :q)"""
            rows = self._all(f"""SELECT du.id, du.username, du.display_name, du.upn, s.name AS source_name {where}
                                 ORDER BY du.display_name, du.id LIMIT :limit OFFSET :offset""", params)
            total = self.db.execute(text(f"SELECT COUNT(*) {where}"), params).scalar()
            items = [{"id": int(r["id"]), "label": r["display_name"] or r["username"], "detail": r["upn"] or r["username"],
                      "source": r["source_name"]} for r in rows]
        elif mode == "group":
            where = """FROM directory_groups dg JOIN identity_sources s ON s.id = dg.identity_source_id
                       WHERE dg.deleted_at IS NULL AND (dg.name LIKE :q OR dg.code LIKE :q OR dg.description LIKE :q)"""
            rows = self._all(f"""SELECT dg.id, dg.name, dg.code, dg.description, s.name AS source_name {where}
                                 ORDER BY dg.name, dg.id LIMIT :limit OFFSET :offset""", params)
            total = self.db.execute(text(f"SELECT COUNT(*) {where}"), params).scalar()
            items = [{"id": int(r["id"]), "label": r["name"], "detail": r["description"] or r["code"], "source": r["source_name"]} for r in rows]
        elif mode in {"root", "folder"}:
            scope, extra, expanding = self._scope()
            column = "sr.root_path" if mode == "folder" else "sr.name"
            where = f"""FROM storage_roots sr JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
                        WHERE sr.deleted_at IS NULL AND (sr.name LIKE :q OR sr.root_path LIKE :q){scope}"""
            rows = self._all(f"""SELECT sr.id, sr.name, sr.root_path, se.name AS endpoint_name {where}
                                 ORDER BY {column}, sr.id LIMIT :limit OFFSET :offset""", {**params, **extra}, expanding)
            total = self.db.execute(text(f"SELECT COUNT(*) {where}").bindparams(*[bindparam(n, expanding=True) for n in expanding]),
                                    {**params, **extra}).scalar()
            items = [{"id": int(r["id"]), "label": r["root_path"] if mode == "folder" else r["name"],
                      "detail": r["name"] if mode == "folder" else r["root_path"], "source": r["endpoint_name"]} for r in rows]
        else:
            raise ValueError("mode")
        return {"items": items, "total": int(total or 0), "offset": offset, "limit": limit}

    # ------------------------------------------------------------ folders reached by a set of account names

    def _reached(self, origins: dict[str, list[dict[str, Any]]], source_id: int, *, offset: int, limit: int,
                 root_id: int | None = None, q: str | None = None) -> dict[str, Any]:
        """The folders whose ACL names one of these keys (account names without domain), paged by folder name.
        origins: key → how the account gets that name (its own, a group, a nested group, the whole company)."""
        named = sorted(k for k, items in origins.items() if any(o["kind"] != "broad" for o in items))
        broad = sorted(k for k, items in origins.items() if any(o["kind"] == "broad" for o in items))
        if not named and not broad:
            return {"items": [], "total": 0, "offset": offset, "limit": limit}
        # A name of the directory never stands for an entry of the server's own namespace: BUILTIN\Administrateurs is
        # the local group of the file server, not the « Administrateurs » group of the domain (Builtin container)
        match = " OR ".join([*([f"(e.principal_key IN :named AND {_NAMESPACE_SQL} NOT IN :local)"] if named else []),
                             *(["e.principal_key IN :broad"] if broad else [])])
        scope, extra, expanding = self._scope()
        where = f"""FROM storage_root_acl_entries e
                    JOIN storage_roots sr ON sr.id = e.storage_root_id AND sr.deleted_at IS NULL
                    JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
                    WHERE ({match}) AND (se.identity_source_id = :src OR se.identity_source_id IS NULL){scope}"""
        params: dict[str, Any] = {"src": int(source_id), **extra, **({"named": named, "local": sorted(LOCAL_NAMESPACES)} if named else {}),
                                  **({"broad": broad} if broad else {})}
        if root_id is not None:
            where += " AND sr.id = :root"
            params["root"] = int(root_id)
        if q:
            where += " AND (sr.name LIKE :rq OR sr.root_path LIKE :rq)"
            params["rq"] = f"%{q.strip()}%"
        names = [*(["named", "local"] if named else []), *(["broad"] if broad else []), *expanding]
        total = self.db.execute(text(f"SELECT COUNT(DISTINCT e.storage_root_id) {where}").bindparams(*[bindparam(n, expanding=True) for n in names]),
                                params).scalar()
        page = self._all(f"""SELECT e.storage_root_id AS id, MIN(sr.name) AS name {where}
                             GROUP BY e.storage_root_id ORDER BY name, id LIMIT :limit OFFSET :offset""",
                         {**params, "limit": limit, "offset": offset}, names)
        ids = [int(r["id"]) for r in page]
        if not ids:
            return {"items": [], "total": int(total or 0), "offset": offset, "limit": limit}
        rows = self._all(
            """SELECT e.storage_root_id, e.principal, e.principal_key, e.raw, sr.name, sr.root_path, sr.discovered_permissions_json,
                      se.name AS endpoint_name
               FROM storage_root_acl_entries e
               JOIN storage_roots sr ON sr.id = e.storage_root_id
               JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
               WHERE e.storage_root_id IN :ids AND e.principal_key IN :keys ORDER BY e.id""",
            {"ids": ids, "keys": sorted({*named, *broad})}, ["ids", "keys"],
        )
        items = folders_from_entries(rows, origins, ids)
        return {"items": items, "total": int(total or 0), "offset": offset, "limit": limit}

    # ------------------------------------------------------------ user

    def user(self, user_id: int, *, offset: int | None = None, limit: int | None = None, include_broad: bool = False,
             root_id: int | None = None, q: str | None = None) -> dict[str, Any] | None:
        offset, limit = _page(offset, limit)
        user = self._one(
            """SELECT du.id, du.identity_source_id, du.external_id, du.username, du.display_name, du.upn, du.email, du.dn,
                      du.object_sid, s.name AS source_name
               FROM directory_users du JOIN identity_sources s ON s.id = du.identity_source_id WHERE du.id = :id""",
            {"id": int(user_id)},
        )
        if user is None:
            return None
        source_id = int(user["identity_source_id"])
        snapshot = self._snapshot(source_id)
        limits = [LIMIT_NTFS_ONLY, LIMIT_SUBFOLDERS, LIMIT_LOCAL_GROUPS]
        state = None
        groups: list[dict[str, Any]] = []
        origins: dict[str, list[dict[str, Any]]] = {}
        for key in {short_name(user.get("username")), short_name(str(user.get("upn") or "").split("@")[0]), str(user.get("object_sid") or "").lower()}:
            if key:
                origins.setdefault(key, []).append({"kind": "direct", "via": [], "account": user.get("username")})
        if snapshot is None:
            limits.append(LIMIT_NO_SNAPSHOT)
        else:
            present = self._one("SELECT is_active FROM directory_snapshot_users WHERE snapshot_id = :s AND external_id = :e",
                                {"s": snapshot["id"], "e": user["external_id"]})
            state = "not_in_directory" if present is None else account_state(present["is_active"], snapshot["account_state_read"])
            if not snapshot["account_state_read"]:
                limits.append(LIMIT_ACCOUNT_STATE)
            walked = self._walk(snapshot["id"], str(user["external_id"]), "up")
            if walked["truncated"]:
                limits.append(LIMIT_DEPTH)
            info = self._groups_by_external(snapshot["id"], source_id, walked["nodes"])
            for external, node in walked["nodes"].items():
                group = info.get(external) or {"name": external, "code": None, "group_id": None}
                via = [(info.get(g) or {}).get("name") or g for g in node["path"]]
                groups.append({"group_id": group.get("group_id"), "name": group["name"], "depth": node["depth"], "via": via,
                               "kind": "group" if node["depth"] == 0 else "nested"})
                origin = {"kind": "group" if node["depth"] == 0 else "nested", "group": group["name"], "via": via, "depth": node["depth"]}
                for key in {short_name(group.get("name")), short_name(group.get("code"))}:
                    if key and key not in broad_keys():
                        origins.setdefault(key, []).append(origin)
        groups.sort(key=lambda g: (g["depth"], str(g["name"]).lower()))
        named = dict(origins)
        broad = {key: [{"kind": "broad", "via": []}] for key in broad_keys()}
        reached = self._reached({**named, **broad} if include_broad else named, source_id, offset=offset, limit=limit, root_id=root_id, q=q)
        if not include_broad:
            reached["broad_total"] = self._reached(broad, source_id, offset=0, limit=1)["total"]
        if any(item["denied"] for item in reached["items"]):
            limits.append(LIMIT_DENY)
        if not self.admin and root_id is None and reached["total"] == 0 and not reached.get("broad_total"):
            # A guardian sees the people of their folders, not the whole directory
            return None
        return {
            "user": {"id": int(user["id"]), "username": user["username"], "display_name": user["display_name"], "upn": user["upn"],
                     "email": user["email"], "dn": user["dn"], "source_name": user["source_name"], "state": state},
            "snapshot_at": (snapshot or {}).get("at"),
            "groups": {"direct": [g for g in groups if g["depth"] == 0], "nested": [g for g in groups if g["depth"] > 0]},
            "folders": reached,
            "limits": limits,
        }

    # ------------------------------------------------------------ group

    def group(self, group_id: int, *, offset: int | None = None, limit: int | None = None, q: str | None = None) -> dict[str, Any] | None:
        offset, limit = _page(offset, limit)
        group = self._one(
            """SELECT dg.id, dg.identity_source_id, dg.external_id, dg.name, dg.code, dg.dn, dg.description, s.name AS source_name
               FROM directory_groups dg JOIN identity_sources s ON s.id = dg.identity_source_id
               WHERE dg.id = :id AND dg.deleted_at IS NULL""",
            {"id": int(group_id)},
        )
        if group is None:
            return None
        source_id = int(group["identity_source_id"])
        snapshot = self._snapshot(source_id)
        limits = [LIMIT_NTFS_ONLY, LIMIT_SUBFOLDERS]
        own = {"kind": "group", "group": group["name"], "via": [], "depth": 0}
        origins: dict[str, list[dict[str, Any]]] = {}
        for key in {short_name(group["name"]), short_name(group.get("code"))}:
            if key:
                origins.setdefault(key, []).append(own)
        parents: list[dict[str, Any]] = []
        nested: list[dict[str, Any]] = []
        members: dict[str, Any] = {"users": [], "groups": [], "users_total": 0}
        exposure = {"effective_users": None, "disabled_users": None}
        if snapshot is None:
            limits.append(LIMIT_NO_SNAPSHOT)
        else:
            up = self._walk(snapshot["id"], str(group["external_id"]), "up")
            down = self._walk(snapshot["id"], str(group["external_id"]), "down")
            if up["truncated"] or down["truncated"]:
                limits.append(LIMIT_DEPTH)
            info = self._groups_by_external(snapshot["id"], source_id, [*up["nodes"], *down["nodes"]])
            for external, node in up["nodes"].items():
                parent = info.get(external) or {"name": external, "code": None, "group_id": None}
                via = [group["name"], *[(info.get(g) or {}).get("name") or g for g in node["path"]]]
                parents.append({"group_id": parent.get("group_id"), "name": parent["name"], "depth": node["depth"], "via": via})
                origin = {"kind": "parent", "group": parent["name"], "via": via, "depth": node["depth"] + 1}
                for key in {short_name(parent.get("name")), short_name(parent.get("code"))}:
                    if key:
                        origins.setdefault(key, []).append(origin)
            for external, node in down["nodes"].items():
                child = info.get(external) or {"name": external, "group_id": None}
                nested.append({"group_id": child.get("group_id"), "name": child["name"], "depth": node["depth"],
                               "via": [(info.get(g) or {}).get("name") or g for g in node["path"]]})
            member_where = """FROM directory_snapshot_memberships m
                              JOIN directory_snapshot_users su ON su.snapshot_id = m.snapshot_id AND su.external_id = m.member_external_id
                              LEFT JOIN directory_users du ON du.identity_source_id = :src AND du.external_id = su.external_id
                              WHERE m.snapshot_id = :s AND m.group_external_id = :g AND m.member_type = 'user'"""
            mp = {"s": snapshot["id"], "g": group["external_id"], "src": source_id}
            members["users_total"] = int(self.db.execute(text(f"SELECT COUNT(*) {member_where}"), mp).scalar() or 0)
            members["users"] = [
                {"user_id": r["user_id"], "username": r["username"], "display_name": r["display_name"],
                 "state": account_state(r["is_active"], snapshot["account_state_read"])}
                for r in self._all(f"""SELECT du.id AS user_id, su.username, su.display_name, su.is_active {member_where}
                                       ORDER BY su.display_name LIMIT 100""", mp)
            ]
            members["groups"] = [g for g in nested if g["depth"] == 0]
            counts = self._one(
                """SELECT COUNT(DISTINCT dem.directory_user_id) AS users,
                          COUNT(DISTINCT CASE WHEN su.is_active = 0 THEN dem.directory_user_id END) AS disabled
                   FROM directory_effective_memberships dem
                   JOIN directory_users du ON du.id = dem.directory_user_id
                   LEFT JOIN directory_snapshot_users su ON su.snapshot_id = :s AND su.external_id = du.external_id
                   WHERE dem.directory_group_id = :g AND (dem.snapshot_id IS NULL OR dem.snapshot_id = :s)""",
                {"s": snapshot["id"], "g": int(group["id"])},
            ) or {}
            exposure = {"effective_users": int(counts.get("users") or 0),
                        "disabled_users": int(counts.get("disabled") or 0) if snapshot["account_state_read"] else None}
            if not snapshot["account_state_read"]:
                limits.append(LIMIT_ACCOUNT_STATE)
        reached = self._reached(origins, source_id, offset=offset, limit=limit, q=q)
        if any(item["denied"] for item in reached["items"]):
            limits.append(LIMIT_DENY)
        if not self.admin and reached["total"] == 0:
            return None
        return {
            "group": {"id": int(group["id"]), "name": group["name"], "code": group["code"], "dn": group["dn"],
                      "description": group["description"], "source_name": group["source_name"],
                      "broad": short_name(group["name"]) in broad_keys()},
            "snapshot_at": (snapshot or {}).get("at"),
            "members": members,
            "nested_groups": sorted(nested, key=lambda g: (g["depth"], str(g["name"]).lower()))[:200],
            "nested_total": len(nested),
            "parent_groups": sorted(parents, key=lambda g: (g["depth"], str(g["name"]).lower()))[:200],
            "folders": reached,
            "exposure": {**exposure, "folders": reached["total"]},
            "limits": limits,
        }

    # ------------------------------------------------------------ folder (a governed folder, or a path below one)

    def resolve_path(self, path: str) -> dict[str, Any] | None:
        """The governed folder holding this path (the deepest one): its rights are the ones read for the path."""
        norm = str(path or "").strip().replace("\\", "/")
        while "//" in norm:
            norm = norm.replace("//", "/")
        norm = norm.rstrip("/").lower()
        if not norm:
            return None
        scope, extra, expanding = self._scope()
        rows = self._all(
            f"""SELECT sr.id, sr.normalized_root_path FROM storage_roots sr
                WHERE sr.deleted_at IS NULL AND (:p = sr.normalized_root_path OR :p LIKE CONCAT(sr.normalized_root_path, '/%')){scope}
                ORDER BY LENGTH(sr.normalized_root_path) DESC LIMIT 1""",
            {"p": norm, **extra}, expanding,
        )
        if not rows:
            return None
        return {"storage_root_id": int(rows[0]["id"]), "below": norm != str(rows[0]["normalized_root_path"] or "")}

    def folder(self, root_id: int, *, offset: int | None = None, limit: int | None = None, level: str | None = None,
               q: str | None = None) -> dict[str, Any] | None:
        offset, limit = _page(offset, limit)
        root = self._one(
            """SELECT sr.id, sr.name, sr.root_path, sr.discovered_permissions_json, se.name AS endpoint_name,
                      se.identity_source_id, se.bind_dn AS endpoint_account, z.name AS zone_name
               FROM storage_roots sr JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id JOIN zones z ON z.id = se.zone_id
               WHERE sr.id = :id AND sr.deleted_at IS NULL""",
            {"id": int(root_id)},
        )
        if root is None:
            return None
        scan = _json(root.get("discovered_permissions_json"))
        source_id = int(root.get("identity_source_id") or 0) or None
        snapshot = self._snapshot(source_id)
        limits = [LIMIT_NTFS_ONLY, LIMIT_LOCAL_GROUPS]
        entries = self._all("SELECT principal, principal_key, raw FROM storage_root_acl_entries WHERE storage_root_id = :id ORDER BY id",
                            {"id": int(root_id)})
        if not scan.get("discovered_at") or not entries:
            limits.append(LIMIT_ACL_NOT_READ)
        keys = sorted({str(e["principal_key"]).lower() for e in entries})
        groups: dict[str, dict[str, Any]] = {}
        users: dict[str, dict[str, Any]] = {}
        if source_id and keys:
            for g in self._all("""SELECT id, name, code FROM directory_groups WHERE identity_source_id = :src AND deleted_at IS NULL
                                  AND (name IN :keys OR code IN :keys)""", {"src": source_id, "keys": keys}, ["keys"]):
                for key in {short_name(g["name"]), short_name(g.get("code"))}:
                    if key in keys:
                        groups[key] = g
            for u in self._all("""SELECT du.id, du.username, du.display_name, du.object_sid, su.is_active
                                  FROM directory_users du
                                  LEFT JOIN directory_snapshot_users su ON su.snapshot_id = :snap AND su.external_id = du.external_id
                                  WHERE du.identity_source_id = :src AND (du.username IN :keys OR du.object_sid IN :keys)""",
                               {"src": source_id, "keys": keys, "snap": (snapshot or {}).get("id") or 0}, ["keys"]):
                for key in {short_name(u.get("username")), str(u.get("object_sid") or "").lower()}:
                    if key in keys:
                        users[key] = u
        broad = broad_keys()
        principals = []
        grants_by_key: dict[str, dict[str, Any]] = {}
        for entry in entries:
            key = str(entry["principal_key"]).lower()
            ace = ace_info(str(entry["principal"]), entry.get("raw"))
            # BUILTIN\\…, NT AUTHORITY\\…: the server's own accounts, never the directory's namesakes
            directory = namespace(ace["principal"]) not in LOCAL_NAMESPACES
            kind = principal_kind(ace["principal"], broad=key in broad, service_account=root.get("endpoint_account"),
                                  group=directory and key in groups, user=directory and key in users)
            row = {**ace, "kind": kind, "group_id": int(groups[key]["id"]) if kind == "group" else None,
                   "user_id": int(users[key]["id"]) if kind == "user" else None}
            principals.append(row)
            if kind in {"group", "user"}:
                current = grants_by_key.get(key)
                # A principal listed twice (explicit and inherited, or allow and deny): the deny, else the strongest
                if current is None or ace["deny"] or (not current["deny"] and _RANK.get(ace["rights"], 0) > _RANK.get(current["rights"], 0)):
                    grants_by_key[key] = {**{k: ace[k] for k in ("principal", "rights", "deny", "inherited")}, "kind": kind}
        if any(p["deny"] for p in principals):
            limits.append(LIMIT_DENY)
        state_read = bool(snapshot and snapshot["account_state_read"])
        direct = [{"user_id": u["id"], "username": u["username"], "display_name": u["display_name"], "key": key, "is_active": u.get("is_active")}
                  for key, u in users.items() if (grants_by_key.get(key) or {}).get("kind") == "user"]
        via_groups: list[dict[str, Any]] = []
        resolved_groups = {key for key, grant in grants_by_key.items() if grant["kind"] == "group"}
        group_ids = {int(g["id"]): key for key, g in groups.items() if key in resolved_groups}
        counts: dict[int, int] = {}
        if group_ids:
            rows = self._all(
                """SELECT dem.directory_group_id AS gid, du.id AS user_id, du.username, du.display_name, MIN(dem.depth) AS depth,
                          MAX(su.is_active) AS is_active
                   FROM directory_effective_memberships dem
                   JOIN directory_users du ON du.id = dem.directory_user_id
                   LEFT JOIN directory_snapshots ds ON ds.id = dem.snapshot_id
                   LEFT JOIN directory_snapshot_users su ON su.snapshot_id = :snap AND su.external_id = du.external_id
                   WHERE dem.directory_group_id IN :gids AND (dem.snapshot_id IS NULL OR UPPER(COALESCE(ds.status, '')) = 'ACTIVE')
                   GROUP BY dem.directory_group_id, du.id, du.username, du.display_name
                   LIMIT :cap""",
                {"gids": sorted(group_ids), "snap": (snapshot or {}).get("id") or 0, "cap": PEOPLE_ROWS_MAX + 1}, ["gids"],
            )
            if len(rows) > PEOPLE_ROWS_MAX:
                rows = rows[:PEOPLE_ROWS_MAX]
                limits.append(LIMIT_PEOPLE_TRUNCATED)
            for r in rows:
                key = group_ids[int(r["gid"])]
                counts[int(r["gid"])] = counts.get(int(r["gid"]), 0) + 1
                via_groups.append({**r, "key": key, "group_name": groups[key]["name"]})
        for row in principals:
            if row["group_id"] is not None:
                row["members"] = counts.get(int(row["group_id"]), 0)
        people = merge_people(direct, via_groups, grants_by_key)
        for person in people:
            person["state"] = account_state(person.pop("is_active", None), state_read)
        if snapshot is not None and not state_read:
            limits.append(LIMIT_ACCOUNT_STATE)
        if snapshot is None:
            limits.append(LIMIT_NO_SNAPSHOT)
        if level in {"read", "write"}:
            people = [p for p in people if (p["ntfs_rights"] in {"modify", "full"}) == (level == "write") and p["ntfs_rights"]]
        if q:
            needle = q.strip().lower()
            people = [p for p in people if needle in str(p.get("display_name") or "").lower() or needle in str(p.get("username") or "").lower()]
        return {
            "folder": {"storage_root_id": int(root["id"]), "name": root["name"], "root_path": root["root_path"],
                       "endpoint_name": root["endpoint_name"], "zone_name": root["zone_name"], "acl_read_at": scan.get("discovered_at"),
                       "inheritance_broken": "PD" in str(scan.get("control") or "").upper().split("|")},
            "snapshot_at": (snapshot or {}).get("at"),
            "principals": principals,
            "summary": {"explicit": sum(1 for p in principals if not p["inherited"]), "inherited": sum(1 for p in principals if p["inherited"]),
                        "broad": sum(1 for p in principals if p["kind"] == "broad" and not p["deny"]),
                        "people": len(people), "write": sum(1 for p in people if p["ntfs_rights"] in {"modify", "full"})},
            "people": {"items": people[offset:offset + limit], "total": len(people), "offset": offset, "limit": limit},
            "limits": limits,
        }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
