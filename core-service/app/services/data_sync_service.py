"""Regular data sync (Advanced Settings › Infrastructure › Schedules), executed by the workers.

1. snapshots : directory snapshot of every active AD source with « Snapshot inventory » on
2. shares    : share discovery of every SMB storage endpoint (roots reachable or not)
3. acl_drift : ACL scan of every governed storage root; the governance alerts then compare the ACL
               and the AD group members (latest snapshot) with the granted accesses
Each part queues jobs; results are applied when the jobs complete (snapshot activation, discovery
sync, root ACL + alerts reconciliation).
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULT_OPTIONS = {"snapshots": True, "shares": True, "acl_drift": True}


def _options(db: Session) -> dict[str, bool]:
    raw = db.execute(text("SELECT options_json FROM infra_schedules WHERE task = 'data_sync'")).scalar()
    try:
        data = json.loads(raw) if isinstance(raw, (str, bytes)) else (raw or {})
    except ValueError:
        data = {}
    return {k: bool(data.get(k, v)) for k, v in DEFAULT_OPTIONS.items()}


def _domain_of(username: str) -> str | None:
    for sep in ("\\", "/"):
        if sep in username:
            return username.split(sep, 1)[0].strip() or None
    return None


async def _sync_snapshots(db: Session) -> dict[str, Any]:
    from app.services.identity_orchestration_service import run_identity_snapshot

    started, skipped, failed = 0, 0, []
    for row in db.execute(
        text(
            """
            SELECT id, name FROM identity_sources
            WHERE is_active = 1 AND LOWER(type) = 'ad'
              AND COALESCE(JSON_VALUE(capabilities, '$.snapshot_enabled'), 'false') IN ('true', '1')
            """
        )
    ).mappings():
        try:
            await run_identity_snapshot({"identity_source_id": int(row["id"]), "mode": "auto"}, None)
            started += 1
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            if detail.get("error_code") == "SNAPSHOT_ALREADY_RUNNING":
                skipped += 1
            else:
                failed.append(f"{row['name']}: {detail.get('message') or exc.detail}")
        except Exception as exc:
            failed.append(f"{row['name']}: {str(exc)[:150]}")
    return {"started": started, "already_running": skipped, "failed": failed}


async def _sync_shares(db: Session) -> dict[str, Any]:
    from app.services.probe_service import submit_probe_run

    started, failed, skipped = 0, [], 0
    for row in db.execute(
        text(
            """
            SELECT id, name, host, port, bind_dn, bind_password_ref
            FROM storage_endpoints
            WHERE LOWER(COALESCE(protocol, 'smb')) IN ('smb', 'cifs') AND host IS NOT NULL AND host <> ''
            """
        )
    ).mappings():
        username = str(row["bind_dn"] or "").strip()
        if not username or not row["bind_password_ref"]:
            skipped += 1  # no account: nothing the worker can read
            continue
        try:
            await submit_probe_run(
                {
                    "kind": "storage-endpoint",
                    "protocol": "smb",
                    "scope": "read",
                    "target": {"host": row["host"], "port": row["port"], "storage_endpoint_id": int(row["id"])},
                    "auth": {"mode": "ntlm", "username": username, "domain": _domain_of(username), "secret_ref": row["bind_password_ref"]},
                    "options": {"timeout_sec": 30, "discover": True},
                    "context": {"storage_endpoint_id": int(row["id"]), "ui_origin": "data_sync", "origin": "data_sync"},
                }
            )
            started += 1
        except Exception as exc:
            failed.append(f"{row['name']}: {str(getattr(exc, 'detail', exc))[:150]}")
    return {"started": started, "skipped_without_account": skipped, "failed": failed}


async def _sync_acl_drift(db: Session) -> dict[str, Any]:
    from app.data.repositories.governance_alerts_repo import GovernanceAlertsRepo
    from app.services.probe_service import submit_probe_run

    roots = [
        dict(r)
        for r in db.execute(
            text(
                """
                SELECT DISTINCT sr.id, sr.name, sr.storage_endpoint_id
                FROM storage_roots sr
                JOIN storage_root_access_profiles srap ON srap.storage_root_id = sr.id
                WHERE sr.deleted_at IS NULL
                """
            )
        ).mappings()
    ]
    started, failed = 0, []
    repo = GovernanceAlertsRepo(db)
    for root in roots:
        # Group members vs grants right away (latest snapshot); the ACL part follows the scan
        repo.reconcile_storage_root(int(root["id"]), commit=False)
        try:
            await submit_probe_run(
                {
                    "kind": "storage-root",
                    "protocol": "smb",
                    "scope": "read",
                    "target": {"storage_root_id": int(root["id"])},
                    "options": {"timeout_sec": 30, "discover_permissions": True},
                    "context": {
                        "storage_root_id": int(root["id"]),
                        "storage_endpoint_id": int(root["storage_endpoint_id"]),
                        "storage_root_name": root["name"],
                        "ui_origin": "data_sync",
                        "origin": "data_sync",
                    },
                }
            )
            started += 1
        except Exception as exc:
            failed.append(f"{root['name']}: {str(getattr(exc, 'detail', exc))[:150]}")
    db.commit()
    return {"roots": len(roots), "acl_scans_started": started, "failed": failed}


async def run_data_sync(db: Session, *, trigger: str) -> dict[str, Any]:
    options = _options(db)
    summary: dict[str, Any] = {"trigger": trigger, "options": options}
    if options["snapshots"]:
        summary["snapshots"] = await _sync_snapshots(db)
    if options["shares"]:
        summary["shares"] = await _sync_shares(db)
    if options["acl_drift"]:
        summary["acl_drift"] = await _sync_acl_drift(db)

    failures = sum(len(part.get("failed") or []) for part in summary.values() if isinstance(part, dict))
    parts = []
    if "snapshots" in summary:
        parts.append(f"{summary['snapshots']['started']} snapshot(s)")
    if "shares" in summary:
        parts.append(f"{summary['shares']['started']} share discovery(ies)")
    if "acl_drift" in summary:
        parts.append(f"{summary['acl_drift']['acl_scans_started']} ACL scan(s)")
    message = ("Started: " + ", ".join(parts)) if parts else "Nothing selected"
    if failures:
        message += f" · {failures} failed to start"
    summary["status"] = "partial" if failures else "success"
    summary["message"] = message
    return summary


def apply_endpoint_discovery(db: Session, *, job_payload: dict[str, Any], result_json: dict[str, Any]) -> None:
    """Share discovery of a data sync completed: mark the roots found or unreachable (like the UI does)."""
    from app.api.storage_roots import StorageRootDiscoverySyncPayload, sync_storage_root_discovery

    payload = (job_payload or {}).get("payload") or {}
    context = payload.get("context") or {}
    if context.get("origin") != "data_sync":
        return
    details = (result_json or {}).get("details") or {}
    if not details.get("discovery_complete"):
        return
    endpoint_id = int(context.get("storage_endpoint_id") or 0)
    if endpoint_id <= 0:
        return
    by_root = details.get("permissions_by_root") or {}
    roots = [
        {"root_path": str(path), "permissions": by_root.get(path) if isinstance(by_root.get(path), list) else []}
        for path in details.get("roots") or []
        if str(path or "").strip()
    ]
    sync_storage_root_discovery(
        StorageRootDiscoverySyncPayload(
            storage_endpoint_id=endpoint_id,
            discovered_at=details.get("discovered_at"),
            discovery_complete=True,
            roots=roots,
        ),
        db=db,
    )
