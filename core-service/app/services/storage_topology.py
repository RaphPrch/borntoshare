"""Storage topology: zone → server → (volume) → share → governed folder, and the DFS namespaces of each zone.

Everything comes from what BornToShare already holds: zones, storage endpoints and their last probe, the governed
folders and their last probe, the FSRM quotas (their server-side path gives the volume: D:\\Partages\\X → D:), the last
measure of each folder, the open alerts and the last reading of each DFS namespace.

States (never guessed):
- available: the last collection succeeded;
- unavailable: the last collection failed;
- degraded: available, but some of what it holds is unavailable (or the DFS reading reported an error);
- unknown: nothing collected yet (or disabled): the absence of data is not an outage.
« stale » is said beside the state: the last collection is older than two cycles of the data synchronisation.

A volume is shown only when an FSRM reading gave it; a share without one hangs under its server, never under a guessed
volume. The folders are never loaded all at once: the overview counts them per server in SQL, a server is counted per
share, and the folders of a share come page by page.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

STATES = ("available", "unavailable", "degraded", "unknown")
DEFAULT_SYNC_MINUTES = 360
PAGE_MAX = 200
_VOLUME = re.compile(r"^\s*([A-Za-z]):")


# ---------------------------------------------------------------- pure computation (tested without a database)


def probe_state(status: Any, *, active: bool = True) -> str:
    """State of one collected element from its last probe."""
    if not active:
        return "unknown"
    value = str(status or "").strip().lower()
    if value == "success":
        return "available"
    if value == "failed":
        return "unavailable"
    return "unknown"


def is_stale(collected_at: Any, stale_before: datetime) -> bool:
    """Collected, but too long ago. Never collected is « unknown », not stale."""
    if collected_at is None:
        return False
    when = collected_at if isinstance(collected_at, datetime) else _parse(collected_at)
    if when is None:
        return False
    return when.replace(tzinfo=None) < stale_before.replace(tzinfo=None)


def aggregate(states: Iterable[str]) -> str:
    """State of a parent from its children. Unknown children are not outages: they are left out, and a parent whose
    children are all unknown (or which has none) is unknown."""
    known = [s for s in states if s != "unknown"]
    if not known:
        return "unknown"
    if all(s == "available" for s in known):
        return "available"
    if all(s == "unavailable" for s in known):
        return "unavailable"
    return "degraded"


def server_state(probe_status: Any, *, active: bool, roots_failed: int, roots_ok: int) -> str:
    """A server answers (available) but some of its folders do not: degraded. A server never probed whose folders
    answer is known through them."""
    own = probe_state(probe_status, active=active)
    if not active:
        return "unknown"
    if own == "unknown":
        return aggregate(["available"] * min(roots_ok, 1) + ["unavailable"] * min(roots_failed, 1))
    if own == "available" and roots_failed:
        return "degraded"
    return own


def counts_state(ok: int, failed: int) -> str:
    """State of a group of folders from its counts (unknown ones left out)."""
    return aggregate(["available"] * min(int(ok or 0), 1) + ["unavailable"] * min(int(failed or 0), 1))


def volume_of(local_path: Any) -> str | None:
    """D:\\Partages\\Finance → D: (the FSRM reading of the quota); anything else: not known."""
    match = _VOLUME.match(str(local_path or ""))
    return f"{match.group(1).upper()}:" if match else None


def share_key(normalized_root_path: Any) -> str | None:
    """/host/share/dir → /host/share (normalized_root_path of the core)."""
    parts = [p for p in str(normalized_root_path or "").split("/") if p]
    return "/" + "/".join(parts[:2]) if len(parts) >= 2 else None


def share_unc(root_path: Any) -> str | None:
    """\\\\host\\share\\dir → \\\\host\\share (as written on the folder, case kept)."""
    parts = [p for p in str(root_path or "").replace("/", "\\").split("\\") if p]
    return "\\\\" + "\\".join(parts[:2]) if len(parts) >= 2 else None


def _parse(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _bytes(value: Any) -> int | None:
    return None if value is None else _int(value)


# ---------------------------------------------------------------- reading


class StorageTopology:
    def __init__(self, db: Session, now: datetime | None = None) -> None:
        self.db = db
        self.now = (now or datetime.now(timezone.utc)).replace(tzinfo=None)
        self.sync_minutes = self._sync_minutes()
        self.stale_before = self.now - timedelta(minutes=2 * self.sync_minutes)

    def _all(self, sql: str, params: dict[str, Any] | None = None, expanding: Iterable[str] = ()) -> list[dict[str, Any]]:
        statement = text(sql)
        for name in expanding:
            statement = statement.bindparams(bindparam(name, expanding=True))
        return [dict(r) for r in self.db.execute(statement, params or {}).mappings().all()]

    def _sync_minutes(self) -> int:
        try:
            value = self.db.execute(text("SELECT interval_minutes FROM infra_schedules WHERE task = 'data_sync'")).scalar()
        except Exception:
            value = None
        return max(15, _int(value) or DEFAULT_SYNC_MINUTES)

    def _freshness(self) -> dict[str, Any]:
        return {"stale_after_minutes": 2 * self.sync_minutes, "stale_before": _iso(self.stale_before)}

    # ------------------------------------------------------------ overview: every zone, its servers and DFS namespaces

    def overview(self) -> dict[str, Any]:
        zones = self._all("SELECT id, name, code, description FROM zones WHERE deleted_at IS NULL ORDER BY name")
        endpoints = self._all(
            """SELECT se.id, se.zone_id, se.name, se.endpoint_type, se.host, se.is_active, se.status, se.last_probe_status,
                      se.last_probe_at, se.last_probe_message,
                      JSON_LENGTH(se.capabilities, '$.dfs_snapshot.links') AS dfs_links,
                      JSON_VALUE(se.capabilities, '$.dfs_snapshot.read_at') AS dfs_read_at,
                      JSON_VALUE(se.capabilities, '$.dfs_snapshot.error') AS dfs_error,
                      JSON_VALUE(se.capabilities, '$.dfs_snapshot.path') AS dfs_path
               FROM storage_endpoints se WHERE se.deleted_at IS NULL ORDER BY se.name"""
        )
        roots = {int(r["eid"]): r for r in self._all(
            """SELECT sr.storage_endpoint_id AS eid, COUNT(*) AS roots,
                      SUM(sr.last_probe_status = 'success') AS ok, SUM(sr.last_probe_status = 'failed') AS failed,
                      SUM(sr.last_probe_at IS NOT NULL AND sr.last_probe_at < :stale) AS stale,
                      COUNT(DISTINCT SUBSTRING_INDEX(sr.normalized_root_path, '/', 3)) AS shares,
                      MAX(sr.last_probe_at) AS last_at
               FROM storage_roots sr WHERE sr.deleted_at IS NULL GROUP BY sr.storage_endpoint_id""",
            {"stale": self.stale_before},
        )}
        quotas = {int(r["eid"]): r for r in self._all(
            """SELECT sr.storage_endpoint_id AS eid, COUNT(*) AS quotas, SUM(q.limit_bytes) AS limit_bytes, SUM(q.used_bytes) AS used_bytes,
                      COUNT(DISTINCT UPPER(LEFT(q.local_path, 2))) AS volumes
               FROM storage_root_quotas q JOIN storage_roots sr ON sr.id = q.storage_root_id AND sr.deleted_at IS NULL
               WHERE q.status = 'applied' GROUP BY sr.storage_endpoint_id"""
        )}
        alerts = self._alerts_by_endpoint()
        by_zone: dict[int, dict[str, list[dict[str, Any]]]] = {}
        for endpoint in endpoints:
            node = self._endpoint_node(endpoint, roots.get(int(endpoint["id"])), quotas.get(int(endpoint["id"])), alerts.get(int(endpoint["id"])))
            kind = "dfs" if node["type"] == "dfs" else "servers"
            by_zone.setdefault(int(endpoint["zone_id"]), {"servers": [], "dfs": []})[kind].append(node)
        out = []
        for zone in zones:
            children = by_zone.get(int(zone["id"]), {"servers": [], "dfs": []})
            nodes = [*children["servers"], *children["dfs"]]
            collected = [n["collected_at"] for n in nodes if n["collected_at"]]
            out.append({
                "id": int(zone["id"]), "type": "zone", "name": zone["name"], "code": zone.get("code"),
                "state": aggregate(n["state"] for n in nodes),
                "stale": any(n["stale"] for n in nodes),
                # The oldest collection of the zone: what the whole zone is known as of
                "collected_at": min(collected) if collected else None,
                "children": {"servers": len(children["servers"]), "dfs": len(children["dfs"]),
                             "roots": sum(n["children"].get("roots", 0) for n in children["servers"])},
                "states": {s: sum(1 for n in nodes if n["state"] == s) for s in STATES},
                "alerts": _sum_alerts(n["alerts"] for n in nodes),
                "capacity": _sum_capacity(n["capacity"] for n in children["servers"]),
                "servers": children["servers"],
                "dfs": children["dfs"],
            })
        return {"zones": out, "freshness": self._freshness(),
                "summary": {"zones": len(out), "servers": sum(z["children"]["servers"] for z in out),
                            "dfs": sum(z["children"]["dfs"] for z in out), "roots": sum(z["children"]["roots"] for z in out),
                            "states": {s: sum(z["states"][s] for z in out) for s in STATES}}}

    def _alerts_by_endpoint(self, endpoint_id: int | None = None) -> dict[int, dict[str, int]]:
        where = " AND COALESCE(ga.storage_endpoint_id, sr.storage_endpoint_id) = :eid" if endpoint_id else ""
        rows = self._all(
            f"""SELECT COALESCE(ga.storage_endpoint_id, sr.storage_endpoint_id) AS eid, COUNT(*) AS open,
                       SUM(ga.severity IN ('critical', 'high')) AS serious
                FROM governance_alerts ga LEFT JOIN storage_roots sr ON sr.id = ga.storage_root_id
                WHERE ga.status = 'open'{where} GROUP BY 1""",
            {"eid": endpoint_id} if endpoint_id else {},
        )
        return {_int(r["eid"]): {"open": _int(r["open"]), "serious": _int(r["serious"])} for r in rows if r["eid"] is not None}

    def _endpoint_node(self, e: dict[str, Any], roots: dict[str, Any] | None, quota: dict[str, Any] | None,
                       alerts: dict[str, int] | None) -> dict[str, Any]:
        active = bool(_int(e.get("is_active"))) and str(e.get("status") or "active").lower() == "active"
        dfs = str(e.get("endpoint_type") or "").lower() == "dfs"
        roots = roots or {}
        if dfs:
            state = probe_state(e.get("last_probe_status"), active=active)
            if state == "available" and e.get("dfs_error"):
                state = "degraded"
            collected = e.get("dfs_read_at") or _iso(e.get("last_probe_at"))
            children = {"links": _int(e.get("dfs_links"))}
        else:
            state = server_state(e.get("last_probe_status"), active=active, roots_failed=_int(roots.get("failed")), roots_ok=_int(roots.get("ok")))
            collected = _iso(e.get("last_probe_at"))
            children = {"roots": _int(roots.get("roots")), "shares": _int(roots.get("shares")), "volumes": _int((quota or {}).get("volumes")),
                        "roots_unavailable": _int(roots.get("failed")), "roots_stale": _int(roots.get("stale"))}
        return {
            "id": int(e["id"]), "type": "dfs" if dfs else "server", "name": e["name"], "host": e.get("host"),
            "path": e.get("dfs_path") if dfs else None, "active": active, "state": state,
            "stale": is_stale(collected, self.stale_before) if state != "unknown" else False,
            "collected_at": collected, "message": e.get("last_probe_message") if state in {"unavailable", "degraded"} else None,
            "children": children, "alerts": alerts or {"open": 0, "serious": 0},
            "capacity": {"quota_limit_bytes": _bytes((quota or {}).get("limit_bytes")), "quota_used_bytes": _bytes((quota or {}).get("used_bytes")),
                         "quotas": _int((quota or {}).get("quotas"))} if not dfs else None,
        }

    # ------------------------------------------------------------ a server: its volumes (when known) and its shares

    def server(self, endpoint_id: int) -> dict[str, Any] | None:
        rows = self._all(
            """SELECT se.id, se.zone_id, z.name AS zone_name, se.name, se.endpoint_type, se.host, se.is_active, se.status,
                      se.last_probe_status, se.last_probe_at, se.last_probe_message, NULL AS dfs_links, NULL AS dfs_read_at,
                      NULL AS dfs_error, NULL AS dfs_path
               FROM storage_endpoints se JOIN zones z ON z.id = se.zone_id
               WHERE se.id = :id AND se.deleted_at IS NULL AND LOWER(se.endpoint_type) <> 'dfs'""",
            {"id": int(endpoint_id)},
        )
        if not rows:
            return None
        endpoint = rows[0]
        shares = self._all(
            """SELECT SUBSTRING_INDEX(sr.normalized_root_path, '/', 3) AS share_key, MIN(sr.root_path) AS sample_path,
                      COUNT(*) AS roots, SUM(sr.last_probe_status = 'success') AS ok, SUM(sr.last_probe_status = 'failed') AS failed,
                      SUM(sr.last_probe_at IS NOT NULL AND sr.last_probe_at < :stale) AS stale, MAX(sr.last_probe_at) AS last_at,
                      MIN(sr.last_probe_at) AS first_at,
                      SUM(CAST(JSON_VALUE(sr.discovered_permissions_json, '$.content_size_bytes') AS UNSIGNED)) AS measured_bytes,
                      COUNT(JSON_VALUE(sr.discovered_permissions_json, '$.content_size_bytes')) AS measured,
                      SUM(q.limit_bytes) AS quota_limit, SUM(q.used_bytes) AS quota_used, COUNT(q.storage_root_id) AS quotas,
                      COUNT(DISTINCT UPPER(LEFT(q.local_path, 2))) AS volume_count, MIN(UPPER(LEFT(q.local_path, 2))) AS volume_raw,
                      SUM(COALESCE(a.open, 0)) AS alerts, SUM(COALESCE(a.serious, 0)) AS serious
               FROM storage_roots sr
               LEFT JOIN storage_root_quotas q ON q.storage_root_id = sr.id AND q.status = 'applied'
               LEFT JOIN (SELECT storage_root_id, COUNT(*) AS open, SUM(severity IN ('critical', 'high')) AS serious
                          FROM governance_alerts WHERE status = 'open' AND storage_root_id IS NOT NULL GROUP BY storage_root_id) a
                 ON a.storage_root_id = sr.id
               WHERE sr.storage_endpoint_id = :id AND sr.deleted_at IS NULL
               GROUP BY 1 ORDER BY 1""",
            {"id": int(endpoint_id), "stale": self.stale_before},
        )
        share_nodes = []
        for s in shares:
            # One volume only when every quota read of the share points to the same one
            volume = volume_of(s.get("volume_raw")) if _int(s.get("volume_count")) == 1 else None
            state = counts_state(_int(s["ok"]), _int(s["failed"]))
            share_nodes.append({
                "key": s["share_key"], "type": "share", "name": share_unc(s["sample_path"]) or s["share_key"], "volume": volume,
                "state": state, "stale": _int(s["stale"]) > 0 and state != "unknown",
                "collected_at": _iso(s["first_at"]), "last_collected_at": _iso(s["last_at"]),
                "children": {"roots": _int(s["roots"]), "roots_unavailable": _int(s["failed"]), "roots_stale": _int(s["stale"]),
                             "roots_unknown": _int(s["roots"]) - _int(s["ok"]) - _int(s["failed"])},
                "capacity": {"quota_limit_bytes": _bytes(s["quota_limit"]), "quota_used_bytes": _bytes(s["quota_used"]), "quotas": _int(s["quotas"]),
                             "measured_bytes": _bytes(s["measured_bytes"]), "measured_roots": _int(s["measured"])},
                "alerts": {"open": _int(s["alerts"]), "serious": _int(s["serious"])},
            })
        volumes: dict[str, dict[str, Any]] = {}
        for share in share_nodes:
            if share["volume"]:
                v = volumes.setdefault(share["volume"], {"key": share["volume"], "type": "volume", "name": share["volume"], "shares": [],
                                                         "capacity": {"quota_limit_bytes": 0, "quota_used_bytes": 0, "quotas": 0}})
                v["shares"].append(share)
                for key in ("quota_limit_bytes", "quota_used_bytes", "quotas"):
                    v["capacity"][key] += share["capacity"][key] or 0
        volume_nodes = []
        for v in volumes.values():
            members = v.pop("shares")
            collected = [s["collected_at"] for s in members if s["collected_at"]]
            volume_nodes.append({**v, "state": aggregate(s["state"] for s in members), "stale": any(s["stale"] for s in members),
                                 "collected_at": min(collected) if collected else None,
                                 "children": {"shares": len(members), "roots": sum(s["children"]["roots"] for s in members)},
                                 "alerts": _sum_alerts(s["alerts"] for s in members)})
        roots_counts = {"ok": sum(_int(s["ok"]) for s in shares), "failed": sum(_int(s["failed"]) for s in shares),
                        "roots": sum(_int(s["roots"]) for s in shares), "stale": sum(_int(s["stale"]) for s in shares),
                        "shares": len(shares)}
        node = self._endpoint_node(endpoint, roots_counts, None, self._alerts_by_endpoint(int(endpoint_id)).get(int(endpoint_id)))
        node["capacity"] = _sum_capacity(s["capacity"] for s in share_nodes)
        node["children"]["volumes"] = len(volume_nodes)
        return {"server": {**node, "zone_id": int(endpoint["zone_id"]), "zone_name": endpoint["zone_name"]},
                "volumes": sorted(volume_nodes, key=lambda v: v["name"]), "shares": share_nodes,
                "shares_without_volume": sum(1 for s in share_nodes if not s["volume"]), "freshness": self._freshness()}

    # ------------------------------------------------------------ the governed folders of a share (or a volume), paged

    def roots(self, endpoint_id: int, *, share: str | None = None, volume: str | None = None, state: str | None = None,
              q: str | None = None, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        offset, limit = max(0, int(offset or 0)), max(1, min(int(limit or 50), PAGE_MAX))
        where = "sr.storage_endpoint_id = :id AND sr.deleted_at IS NULL"
        params: dict[str, Any] = {"id": int(endpoint_id), "stale": self.stale_before}
        if share:
            where += " AND (sr.normalized_root_path = :share OR sr.normalized_root_path LIKE :share_like)"
            params.update(share=share.lower(), share_like=share.lower().replace("%", r"\%").replace("_", r"\_") + "/%")
        if volume:
            where += " AND q.local_path LIKE :vol"
            params["vol"] = f"{volume[:1]}:%"
        if state == "available":
            where += " AND sr.last_probe_status = 'success'"
        elif state == "unavailable":
            where += " AND sr.last_probe_status = 'failed'"
        elif state == "unknown":
            where += " AND (sr.last_probe_status IS NULL OR sr.last_probe_status NOT IN ('success', 'failed'))"
        elif state == "stale":
            where += " AND sr.last_probe_at < :stale"
        if q:
            where += " AND (sr.name LIKE :q OR sr.root_path LIKE :q)"
            params["q"] = f"%{q.strip()}%"
        base = f"""FROM storage_roots sr LEFT JOIN storage_root_quotas q ON q.storage_root_id = sr.id AND q.status = 'applied'
                   WHERE {where}"""
        total = _int(self.db.execute(text(f"SELECT COUNT(*) {base}"), params).scalar())
        rows = self._all(
            f"""SELECT sr.id, sr.name, sr.root_path, sr.last_probe_status, sr.last_probe_at, sr.last_probe_message, sr.status,
                       CAST(JSON_VALUE(sr.discovered_permissions_json, '$.content_size_bytes') AS UNSIGNED) AS measured_bytes,
                       JSON_VALUE(sr.discovered_permissions_json, '$.content_updated_at') AS measured_at,
                       q.limit_bytes, q.used_bytes, q.local_path
                {base} ORDER BY sr.root_path, sr.id LIMIT :limit OFFSET :offset""",
            {**params, "limit": limit, "offset": offset},
        )
        ids = [int(r["id"]) for r in rows]
        alerts = {int(r["rid"]): r for r in self._all(
            """SELECT storage_root_id AS rid, COUNT(*) AS open, SUM(severity IN ('critical', 'high')) AS serious
               FROM governance_alerts WHERE status = 'open' AND storage_root_id IN :ids GROUP BY storage_root_id""",
            {"ids": ids}, ["ids"],
        )} if ids else {}
        items = []
        for r in rows:
            node_state = probe_state(r["last_probe_status"])
            items.append({
                "id": int(r["id"]), "type": "root", "name": r["name"], "path": r["root_path"], "state": node_state,
                "stale": node_state != "unknown" and is_stale(r["last_probe_at"], self.stale_before),
                "collected_at": _iso(r["last_probe_at"]), "message": r["last_probe_message"] if node_state == "unavailable" else None,
                "volume": volume_of(r["local_path"]),
                "capacity": {"quota_limit_bytes": _bytes(r["limit_bytes"]), "quota_used_bytes": _bytes(r["used_bytes"]),
                             "measured_bytes": _bytes(r["measured_bytes"]), "measured_at": r["measured_at"]},
                "alerts": {"open": _int((alerts.get(int(r["id"])) or {}).get("open")), "serious": _int((alerts.get(int(r["id"])) or {}).get("serious"))},
            })
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    # ------------------------------------------------------------ a DFS namespace: its folders and where they lead, paged

    def dfs(self, endpoint_id: int, *, offset: int = 0, limit: int = 50, q: str | None = None) -> dict[str, Any] | None:
        from app.data.models.storage_endpoint import StorageEndpoint
        from app.services.dfs_links import describe_links, snapshot

        endpoint = self.db.get(StorageEndpoint, int(endpoint_id))
        if endpoint is None or getattr(endpoint, "deleted_at", None) is not None or str(endpoint.endpoint_type or "").lower() != "dfs":
            return None
        offset, limit = max(0, int(offset or 0)), max(1, min(int(limit or 50), PAGE_MAX))
        shot = snapshot(endpoint)
        links = describe_links(self.db, endpoint)
        if q:
            needle = q.strip().lower()
            links = [link for link in links if needle in str(link.get("dfs_path") or "").lower()
                     or any(needle in str(t.get("unc") or "").lower() for t in link.get("targets") or [])]
        page = links[offset:offset + limit]
        root_ids = sorted({int(t["storage_root_id"]) for link in page for t in link["targets"] if t.get("storage_root_id")})
        states = {int(r["id"]): r for r in self._all(
            "SELECT id, name, last_probe_status, last_probe_at FROM storage_roots WHERE id IN :ids AND deleted_at IS NULL",
            {"ids": root_ids}, ["ids"],
        )} if root_ids else {}
        for link in page:
            for target in link["targets"]:
                row = states.get(int(target.get("storage_root_id") or 0))
                target["state"] = probe_state(row["last_probe_status"]) if row else "unknown"
                target["storage_root_name"] = row["name"] if row else None
            link["target_state"] = aggregate(t["state"] for t in link["targets"])
        zone = self.db.execute(text("SELECT name FROM zones WHERE id = :id"), {"id": int(endpoint.zone_id)}).scalar()
        dfs_row = {"id": int(endpoint.id), "zone_id": int(endpoint.zone_id), "name": endpoint.name, "endpoint_type": "dfs",
                   "host": endpoint.host, "is_active": endpoint.is_active, "status": endpoint.status,
                   "last_probe_status": endpoint.last_probe_status, "last_probe_at": endpoint.last_probe_at,
                   "last_probe_message": endpoint.last_probe_message, "dfs_links": len(snapshot(endpoint).get("links") or []),
                   "dfs_read_at": shot.get("read_at"), "dfs_error": shot.get("error"), "dfs_path": shot.get("path")}
        node = self._endpoint_node(dfs_row, None, None, None)
        return {"dfs": {**node, "zone_name": zone, "error": shot.get("error"),
                        "link_states": {s: sum(1 for link in links if link["state"] == s) for s in
                                        ("managed", "partial", "to_manage", "unknown_server", "no_target")}},
                "links": {"items": page, "total": len(links), "offset": offset, "limit": limit}, "freshness": self._freshness()}


def _sum_alerts(items: Iterable[dict[str, int]]) -> dict[str, int]:
    out = {"open": 0, "serious": 0}
    for item in items:
        out["open"] += _int((item or {}).get("open"))
        out["serious"] += _int((item or {}).get("serious"))
    return out


def _sum_capacity(items: Iterable[dict[str, Any] | None]) -> dict[str, Any]:
    """Sums of what is known; None when nothing is (never a 0 that would read as « empty »)."""
    out: dict[str, Any] = {}
    for item in items:
        for key, value in (item or {}).items():
            if key.endswith("_at"):
                continue
            if value is not None:
                out[key] = (out.get(key) or 0) + value
            else:
                out.setdefault(key, None)
    return out
