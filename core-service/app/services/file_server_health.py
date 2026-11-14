"""Scheduled check of the file servers (Advanced Settings › Infrastructure › Schedules › File servers; task « dfs_read »).

Each file server is tested by a worker with its own account (the same test as « Test » on its page); options:
- folders: its governed folders too (reached, ACL read), as « Read the ACL » on each one;
- dfs: the DFS namespaces read again, so that the DFS folders added or removed outside BornToShare show.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

TASK = "dfs_read"
DEFAULT_OPTIONS = {"folders": False, "dfs": True}


def options(db: Session) -> dict[str, bool]:
    raw = db.execute(text("SELECT options_json FROM infra_schedules WHERE task = :task"), {"task": TASK}).scalar()
    try:
        data = json.loads(raw) if isinstance(raw, (str, bytes)) else (raw or {})
    except ValueError:
        data = {}
    return {key: bool(data.get(key, default)) for key, default in DEFAULT_OPTIONS.items()}


def _domain_of(username: str) -> str | None:
    for sep in ("\\", "/"):
        if sep in username:
            return username.split(sep, 1)[0].strip() or None
    return None


async def run_file_servers(db: Session, *, trigger: str) -> dict[str, Any]:
    from app.services.dfs_refresh import run_dfs_read
    from app.services.probe_service import submit_probe_run

    chosen = options(db)
    servers = [dict(row) for row in db.execute(text(
        """
        SELECT id, name, host, port, bind_dn, bind_password_ref
        FROM storage_endpoints
        WHERE LOWER(COALESCE(endpoint_type, 'smb')) <> 'dfs' AND LOWER(COALESCE(protocol, 'smb')) IN ('smb', 'cifs')
          AND COALESCE(is_active, 1) = 1 AND host IS NOT NULL AND host <> ''
        """
    )).mappings()]
    tested, skipped, folders = 0, 0, 0
    errors: list[str] = []
    for server in servers:
        username = str(server["bind_dn"] or "").strip()
        if not username or not server["bind_password_ref"]:
            skipped += 1  # no account: nothing the worker can test
            continue
        try:
            await submit_probe_run({
                "kind": "storage-endpoint", "protocol": "smb", "scope": "read",
                "target": {"host": server["host"], "port": server["port"], "storage_endpoint_id": int(server["id"])},
                "auth": {"mode": "ntlm", "username": username, "domain": _domain_of(username), "secret_ref": server["bind_password_ref"]},
                "options": {"timeout_sec": 30, "discover": False},
                "context": {"storage_endpoint_id": int(server["id"]), "ui_origin": "file_server_health", "origin": "file_server_health"},
            })
            tested += 1
        except Exception as exc:
            errors.append(f"{server['name']}: {str(getattr(exc, 'detail', exc))[:150]}")
            continue
        if not chosen["folders"]:
            continue
        for root in db.execute(text("SELECT id, name FROM storage_roots WHERE storage_endpoint_id = :id AND deleted_at IS NULL"),
                               {"id": int(server["id"])}).mappings():
            try:
                await submit_probe_run({
                    "kind": "storage-root", "protocol": "smb", "scope": "read",
                    "target": {"storage_root_id": int(root["id"])},
                    "options": {"timeout_sec": 30},
                    "context": {"storage_root_id": int(root["id"]), "storage_endpoint_id": int(server["id"]), "storage_root_name": root["name"],
                                "ui_origin": "file_server_health", "origin": "file_server_health"},
                })
                folders += 1
            except Exception as exc:
                errors.append(f"{root['name']}: {str(getattr(exc, 'detail', exc))[:150]}")
    message = f"{tested} serveur(s) de fichiers testé(s), {skipped} sans compte"
    if chosen["folders"]:
        message += f", {folders} dossier(s) contrôlé(s)"
    summary: dict[str, Any] = {"servers": tested, "skipped_without_account": skipped, "folders": folders, "errors": errors, "options": chosen}
    if chosen["dfs"]:
        dfs = await run_dfs_read(db, trigger=trigger)
        summary["dfs"] = dfs
        message += f" · {dfs['message']}"
        if dfs["status"] != "success":
            errors.append(dfs["message"])
    if errors:
        message += f" · {'; '.join(errors)[:300]}"
    status = "failed" if errors and not tested else "partial" if errors else "success"
    return {**summary, "status": status, "message": message}
