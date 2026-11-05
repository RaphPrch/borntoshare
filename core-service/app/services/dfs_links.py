"""DFS namespaces declared in BornToShare: their folders, the file server folders they lead to, the managed ones.

A namespace is a storage endpoint of type « dfs ». Its last reading (folders and targets, by the worker) is kept in
its capabilities. A target \\\\FILER01\\Share\\Dir is a declared file server when FILER01 resolves to its host (Advanced
settings > Network and DNS); the folder is managed when that server has the storage root \\\\<host>\\Share\\Dir.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import domain_dns
from app.services.storage_guards import same_host


def _norm(path: str) -> str:
    raw = str(path or "").strip().replace("/", "\\")
    while "\\\\" in raw[2:]:
        raw = raw[:2] + raw[2:].replace("\\\\", "\\")
    return raw.rstrip("\\").lower()


def split_unc(path: str) -> tuple[str, str]:
    """(server, rest) of \\\\server\\share\\dir."""
    parts = [part for part in str(path or "").replace("/", "\\").split("\\") if part]
    return (parts[0], "\\".join(parts[1:])) if parts else ("", "")


class _Servers:
    """The declared file servers, matched to a DFS target server by name, alias or address."""

    def __init__(self, db: Session) -> None:
        self.dns = domain_dns.effective(db)
        self.rows = [
            dict(row)
            for row in db.execute(
                text("SELECT id, name, host FROM storage_endpoints WHERE LOWER(endpoint_type) <> 'dfs' AND host IS NOT NULL")
            ).mappings().all()
        ]
        self._addresses: dict[str, set[str]] = {}

    def _of(self, host: str) -> set[str]:
        key = host.lower()
        if key not in self._addresses:
            self._addresses[key] = domain_dns.addresses(host, self.dns)
        return self._addresses[key]

    def match(self, server: str) -> dict[str, Any] | None:
        short = str(server or "").split(".")[0].lower()
        for row in self.rows:
            if same_host(str(row["host"]), server):
                return row
        # A DFS target names the server as Windows knows it (FILER01), often declared here by its address:
        # its declared name, or the first label of its host, says it too
        for row in self.rows:
            if short and short in {str(row.get("name") or "").strip().lower(), str(row["host"]).split(".")[0].lower()}:
                return row
        wanted = self._of(server)
        if not wanted:
            return None
        return next((row for row in self.rows if wanted & self._of(str(row["host"]))), None)


def _roots_by_path(db: Session) -> dict[tuple[int, str], int]:
    rows = db.execute(text("SELECT id, storage_endpoint_id, root_path FROM storage_roots")).mappings().all()
    return {(int(r["storage_endpoint_id"]), _norm(r["root_path"])): int(r["id"]) for r in rows}


def snapshot(endpoint: Any) -> dict[str, Any]:
    caps = endpoint.capabilities if isinstance(endpoint.capabilities, dict) else {}
    value = caps.get("dfs_snapshot")
    return value if isinstance(value, dict) else {}


def describe_links(db: Session, endpoint: Any, *, servers: _Servers | None = None, roots: dict | None = None) -> list[dict[str, Any]]:
    """Every DFS folder of the namespace, its targets on declared servers, and its state."""
    servers = servers or _Servers(db)
    roots = roots if roots is not None else _roots_by_path(db)
    out = []
    for link in snapshot(endpoint).get("links") or []:
        targets = []
        for unc in link.get("targets") or []:
            server, rest = split_unc(unc)
            row = servers.match(server) if server else None
            local = f"\\\\{row['host']}\\{rest}" if row else None
            targets.append(
                {
                    "unc": unc,
                    "server": server,
                    "storage_endpoint_id": int(row["id"]) if row else None,
                    "storage_endpoint_name": row["name"] if row else None,
                    "root_path": local,
                    "storage_root_id": roots.get((int(row["id"]), _norm(local))) if row else None,
                }
            )
        if not targets:
            state = "no_target"
        elif any(t["storage_endpoint_id"] is None for t in targets):
            state = "unknown_server"
        elif all(t["storage_root_id"] for t in targets):
            state = "managed"
        elif any(t["storage_root_id"] for t in targets):
            state = "partial"
        else:
            state = "to_manage"
        out.append(
            {
                "path": link.get("path"),
                "dfs_path": f"{snapshot(endpoint).get('path') or ''}\\{link.get('path')}",
                "targets": targets,
                "state": state,
            }
        )
    return out


_cache: tuple[float, tuple[dict[int, str], dict[int, list[int]]]] | None = None
_CACHE_SECONDS = 60


def store_snapshot(db: Session, endpoint: Any, namespace: dict[str, Any]) -> int:
    """Keep a reading of the namespace by the worker on its endpoint; the number of DFS folders it has."""
    from datetime import datetime, timezone

    capabilities = dict(endpoint.capabilities or {})
    capabilities["dfs_snapshot"] = {
        "path": namespace.get("path"),
        "name": namespace.get("name"),
        "type": namespace.get("type"),
        "root_targets": list(namespace.get("root_targets") or []),
        "links": [
            {"path": str(link.get("path")), "targets": [str(t) for t in (link.get("targets") or [])]}
            for link in (namespace.get("links") or [])
            if isinstance(link, dict) and link.get("path")
        ],
        "error": namespace.get("error"),
        "read_at": datetime.now(timezone.utc).isoformat(),
    }
    endpoint.capabilities = capabilities
    db.commit()
    forget_cache()
    return len(capabilities["dfs_snapshot"]["links"])


def forget_cache() -> None:
    global _cache
    _cache = None


def dfs_paths_and_replicas(db: Session) -> tuple[dict[int, str], dict[int, list[int]]]:
    """DFS path of each managed storage root, and the other targets of the same DFS folder (replicas).

    Kept one minute: the namespaces change rarely, and matching their targets asks the DNS.
    """
    import time

    global _cache
    if _cache and time.monotonic() - _cache[0] < _CACHE_SECONDS:
        return _cache[1]
    result = _compute(db)
    _cache = (time.monotonic(), result)
    return result


def _compute(db: Session) -> tuple[dict[int, str], dict[int, list[int]]]:
    from app.data.models.storage_endpoint import StorageEndpoint

    namespaces = db.query(StorageEndpoint).filter(StorageEndpoint.endpoint_type == "dfs").all()
    if not namespaces:
        return {}, {}
    servers = _Servers(db)
    roots = _roots_by_path(db)
    paths: dict[int, str] = {}
    replicas: dict[int, list[int]] = {}
    for namespace in namespaces:
        for link in describe_links(db, namespace, servers=servers, roots=roots):
            ids = [t["storage_root_id"] for t in link["targets"] if t["storage_root_id"]]
            for root_id in ids:
                paths.setdefault(root_id, link["dfs_path"])
                replicas[root_id] = sorted({*replicas.get(root_id, []), *[other for other in ids if other != root_id]})
    return paths, replicas
