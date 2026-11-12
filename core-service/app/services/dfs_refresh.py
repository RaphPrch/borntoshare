"""Scheduled reading of every DFS namespace (Advanced Settings › Infrastructure › Schedules › DFS namespaces).

A DFS folder added or removed outside BornToShare (DFS console) shows without anyone pressing « Read again »:
each namespace is read by a worker with its own account, and the reading is kept like a manual one.
"""
from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.orm import Session

from app.data.models.storage_endpoint import StorageEndpoint
from app.services.activity_log import log_activity

READ_TIMEOUT_SECONDS = 150


async def _read_namespace(endpoint: StorageEndpoint, path: str, namespace_type: str | None) -> tuple[dict[str, Any] | None, str]:
    from app.services.probe_service import fetch_probe_job, submit_probe_run

    # \\\\corp.local\\brest: the worker needs the domain to give back the domain path, not the one of its root server
    domain = [part for part in path.split("\\") if part][0] if namespace_type == "domain" else None
    queued = await submit_probe_run({
        "kind": "storage-endpoint", "protocol": "dfs", "scope": "read",
        "target": {"host": endpoint.host, "port": int(endpoint.port or 445), "path": path, **({"domain": domain} if domain else {})},
        "auth": {"mode": "ntlm", "username": endpoint.bind_dn, "secret_ref": endpoint.bind_password_ref},
        "options": {"timeout_sec": 120},
        "context": {"ui_origin": "dfs_read", "storage_endpoint_id": int(endpoint.id)},
    })
    job_id = int((queued or {}).get("job_id") or 0)
    for _ in range(READ_TIMEOUT_SECONDS // 3):
        job = dict(await fetch_probe_job(job_id) or {})
        state = str(job.get("status") or "").lower()
        if state == "succeeded":
            result = job.get("result") if isinstance(job.get("result"), dict) else {}
            namespaces = ((result.get("details") or {}).get("namespaces")) or []
            return (namespaces[0], "") if namespaces else (None, "This namespace was not found on its server.")
        if state in {"failed", "timed_out", "cancelled"}:
            error = job.get("error") if isinstance(job.get("error"), dict) else {}
            return None, str(error.get("message") or state)
        await asyncio.sleep(3)
    return None, "The worker did not answer in time."


async def run_dfs_read(db: Session, *, trigger: str) -> dict[str, Any]:
    from app.services.dfs_links import snapshot, store_snapshot

    read, failed, skipped = 0, 0, 0
    errors: list[str] = []
    endpoints = db.query(StorageEndpoint).filter(StorageEndpoint.endpoint_type == "dfs").all()
    for endpoint in endpoints:
        shot = snapshot(endpoint)
        path = str(shot.get("path") or "").strip()
        if not endpoint.is_active or not path or not (endpoint.host and endpoint.bind_dn and endpoint.bind_password_ref):
            skipped += 1
            continue
        namespace, error = await _read_namespace(endpoint, path, shot.get("type"))
        if namespace is None or str(namespace.get("path") or "").strip().lower() != path.lower():
            failed += 1
            errors.append(f"{endpoint.name}: {error or 'another namespace was read'}")
            continue
        links = store_snapshot(db, endpoint, namespace)
        read += 1
        log_activity(
            db, actor_type="system", actor_id=None, actor_display="scheduler",
            action="storage_endpoint.dfs_read", outcome="success", target_type="storage_endpoint", target_id=int(endpoint.id),
            target_display=str(endpoint.name), context_json={"links": links, "path": path, "trigger": trigger},
        )
    status = "failed" if failed and not read else "partial" if failed else "success"
    message = f"{read} espace(s) de noms relu(s), {failed} en échec, {skipped} ignoré(s)" + (f" · {'; '.join(errors)[:300]}" if errors else "")
    return {"status": status, "message": message, "read": read, "failed": failed, "skipped": skipped}
