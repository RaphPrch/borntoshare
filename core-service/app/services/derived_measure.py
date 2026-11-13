"""A governed folder declared inside a folder already measured: it is measured too.

The 5S module holds the last measure of the parent (every sub-folder, every file, the fingerprints), and the core the
last sensitivity scan: the child gets its part of both at once, marked « derived » (method), until its own measures
replace them. Never a folder shown empty when the data of its content is already in the databases.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _parts(root_path: str) -> list[str]:
    return [part for part in re.split(r"[\\/]+", str(root_path or "")) if part]


def _measured(root: Any) -> bool:
    payload = root.discovered_permissions_json if isinstance(root.discovered_permissions_json, dict) else {}
    return isinstance(payload.get("content_stats"), dict) and not payload.get("content_interim")


def ancestor_of(db: Session, root: Any) -> Any | None:
    """The closest governed folder above this one (same server and share) that has a measure of its own."""
    from app.data.models.storage_root import StorageRoot

    mine = [part.lower() for part in _parts(root.root_path)]
    best, best_len = None, 0
    for other in db.query(StorageRoot).filter(StorageRoot.storage_endpoint_id == root.storage_endpoint_id).all():
        if int(other.id) == int(root.id) or not _measured(other):
            continue
        theirs = [part.lower() for part in _parts(other.root_path)]
        if len(theirs) < len(mine) and mine[:len(theirs)] == theirs and len(theirs) > best_len:
            payload = other.discovered_permissions_json or {}
            if (payload.get("content_stats") or {}).get("method") == "derived":
                continue  # only from a real measure
            best, best_len = other, len(theirs)
    return best


def child_findings(findings: list[dict], parent_root_path: str, child_root_path: str) -> list[dict]:
    """The findings of the parent's scan that lie in the child folder, their paths from the child (as its own scan)."""
    parent_base = "\\".join(_parts(parent_root_path)[2:])
    child_base = "\\".join(_parts(child_root_path)[2:])
    inner = child_base[len(parent_base):].strip("\\") if child_base.lower().startswith(parent_base.lower()) else child_base
    mine = []
    for item in findings:
        path = str((item or {}).get("path") or "").strip("\\")
        if parent_base and path.lower().startswith(parent_base.lower() + "\\"):
            path = path[len(parent_base) + 1:]
        if inner and path.lower().startswith(inner.lower() + "\\"):
            mine.append({**item, "path": path[len(inner) + 1:]})
    return mine


def _derive_sensitivity(db: Session, parent: Any, child: Any) -> bool:
    from app.services import sensitivity

    row = db.execute(text("""SELECT findings_json, summary_json, scanned_at, rules_version, content_complete FROM storage_root_sensitivity
                             WHERE storage_root_id = :id AND status = 'done'"""), {"id": int(parent.id)}).mappings().first()
    if not row:
        return False
    if db.execute(text("SELECT 1 FROM storage_root_sensitivity WHERE storage_root_id = :id AND status = 'done'"), {"id": int(child.id)}).first():
        return False  # it has a scan of its own
    mine = child_findings(json.loads(row["findings_json"] or "[]"), parent.root_path, child.root_path)
    flagged, counts = sensitivity.visible(mine, set(), len(mine))
    summary = {**json.loads(row["summary_json"] or "{}"), "files_flagged_total": len(mine), "derived_from": int(parent.id)}
    db.execute(text("""INSERT INTO storage_root_sensitivity (storage_root_id, status, files_flagged, counts_json, findings_json, summary_json,
                         scanned_at, content_complete, rules_version)
                       VALUES (:id, 'done', :flagged, :counts, :findings, :summary, :at, :complete, :rules)
                       ON DUPLICATE KEY UPDATE status = 'done', files_flagged = VALUES(files_flagged), counts_json = VALUES(counts_json),
                         findings_json = VALUES(findings_json), summary_json = VALUES(summary_json), scanned_at = VALUES(scanned_at),
                         content_complete = VALUES(content_complete), rules_version = VALUES(rules_version), error_message = NULL"""),
               {"id": int(child.id), "flagged": flagged, "counts": json.dumps(counts), "findings": json.dumps(mine[:500]),
                "summary": json.dumps(summary), "at": row["scanned_at"], "complete": row["content_complete"], "rules": row["rules_version"]})
    return True


def derive(db: Session, root_id: int) -> bool:
    """Gives a folder never measured its part of the measure (and sensitivity scan) of the closest measured folder above it."""
    from app.data.models.storage_root import StorageRoot
    from app.services import modules

    root = db.get(StorageRoot, int(root_id))
    if root is None or _measured(root):
        return False
    parent = ancestor_of(db, root)
    if parent is None:
        return False
    path = "\\".join(_parts(root.root_path)[2:])
    answer = modules.derive(int(parent.id), int(root.id), path)
    if not answer or not answer.get("derived"):
        return False
    stats = dict(answer.get("stats") or {})
    measured_at = str(stats.pop("measured_at", "") or datetime.now(timezone.utc).isoformat())
    current = dict(root.discovered_permissions_json) if isinstance(root.discovered_permissions_json, dict) else {}
    root.discovered_permissions_json = {**current, "content_stats": stats, "content_size_bytes": int(stats.get("bytes") or 0),
                                        "content_updated_at": measured_at.replace("Z", "+00:00"), "content_interim": False,
                                        "content_derived_from": int(parent.id)}
    db.execute(text("""INSERT INTO storage_root_scans (storage_root_id, status, method, finished_at, files, error_message)
                       VALUES (:id, 'done', 'derived', UTC_TIMESTAMP(), :files, NULL)
                       ON DUPLICATE KEY UPDATE status = 'done', method = 'derived', finished_at = VALUES(finished_at), files = VALUES(files), error_message = NULL"""),
               {"id": int(root.id), "files": int(stats.get("files") or 0)})
    try:
        _derive_sensitivity(db, parent, root)
    except Exception:
        db.rollback()
        logger.warning("DERIVED_SENSITIVITY_FAILED", exc_info=True)
    db.commit()
    try:
        from app.services.policies import run_all

        run_all(db, only_root_ids={int(root.id)}, trigger="derived_measure", allow_jobs=False)
    except Exception:
        db.rollback()
    logger.info("DERIVED_MEASURE", extra={"storage_root_id": int(root.id), "from": int(parent.id)})
    return True


def derive_missing(db: Session) -> int:
    """Every governed folder never measured that sits inside a measured one (folders declared before this existed)."""
    from app.data.models.storage_root import StorageRoot

    done = 0
    for root in db.query(StorageRoot).all():
        if not _measured(root):
            try:
                done += 1 if derive(db, int(root.id)) else 0
            except Exception:
                db.rollback()
                logger.warning("DERIVED_MEASURE_FAILED", exc_info=True)
    return done
