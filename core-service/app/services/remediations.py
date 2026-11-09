"""Corrections asked to guardians for the passwords found in their folders (pack 155).

An administrator asks the guardians of a folder to remove or move the files holding passwords, before a due date:
- while it is open, the folder has an alert « correction asked » (its to-do list), and the guardians get an e-mail
  when notifications are on;
- every new scan of the folder looks again: no password file left → the correction is done by itself;
- at the due date the policies run (schedule « policies ») scans the folder again; still there → overdue, and the
  alert becomes critical.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

logger = logging.getLogger("core.remediations")
OPEN_STATES = ("open", "overdue")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: Any) -> str | None:
    return value.isoformat() + "Z" if value else None


def _row(row: Any) -> dict[str, Any]:
    try:
        paths = json.loads(row["paths_json"]) if row["paths_json"] else []
    except ValueError:
        paths = []
    return {
        "id": int(row["id"]), "storage_root_id": int(row["storage_root_id"]), "status": row["status"],
        "files_at_request": int(row["files_at_request"] or 0), "paths": paths, "note": row["note"],
        "requested_by": row["requested_by"], "requested_at": _iso(row["requested_at"]), "due_at": _iso(row["due_at"]),
        "rescan_requested_at": _iso(row["rescan_requested_at"]), "closed_at": _iso(row["closed_at"]), "closed_by": row["closed_by"],
    }


def password_paths(db: Session, storage_root_id: int) -> list[str]:
    """The files holding passwords in the last scan (without the false positives)."""
    from app.services import sensitivity

    scan = sensitivity.get(db, int(storage_root_id)) or {}
    if scan.get("status") != "done":
        return []
    return sorted({item["path"] for item in scan.get("findings") or []
                   if item.get("category") in sensitivity.PASSWORD_CATEGORIES and not item.get("ignored")})


def current(db: Session, storage_root_id: int) -> dict[str, Any] | None:
    row = db.execute(
        text("SELECT * FROM sensitivity_remediations WHERE storage_root_id = :id AND status IN ('open', 'overdue') ORDER BY id DESC LIMIT 1"),
        {"id": int(storage_root_id)},
    ).mappings().first()
    return _row(row) if row else None


def history(db: Session, storage_root_id: int, limit: int = 5) -> list[dict[str, Any]]:
    rows = db.execute(
        text("SELECT * FROM sensitivity_remediations WHERE storage_root_id = :id ORDER BY id DESC LIMIT :limit"),
        {"id": int(storage_root_id), "limit": int(limit)},
    ).mappings().all()
    return [_row(row) for row in rows]


def _alert_key(remediation_id: int) -> str:
    return f"remediation:{int(remediation_id)}"


def _alert(db: Session, item: dict[str, Any], *, overdue: bool) -> None:
    from app.data.repositories.governance_alerts_repo import GovernanceAlertsRepo

    root = db.execute(text("SELECT name, root_path FROM storage_roots WHERE id = :id"), {"id": item["storage_root_id"]}).mappings().first() or {}
    due = item["due_at"][:10] if item.get("due_at") else ""
    GovernanceAlertsRepo(db)._upsert_alert({
        "alert_key": _alert_key(item["id"]),
        "scope_type": "storage_root",
        "scope_id": item["storage_root_id"],
        "alert_type": "sensitivity_remediation",
        "severity": "critical" if overdue else "warning",
        "title": "Correction en retard : mots de passe toujours présents" if overdue else "Correction demandée : mots de passe à retirer",
        "message": (f"{item['files_at_request']} fichier(s) contenant des mots de passe à retirer ou déplacer avant le {due}."
                    + (f" {item['note']}" if item.get("note") else "")),
        "source_type": "remediation",
        "source_id": str(item["id"]),
        "storage_root_id": item["storage_root_id"],
        "metadata_json": {"remediation_id": item["id"], "paths": item.get("paths", [])[:20], "storage_root_name": root.get("name")},
    })


def _resolve_alert(db: Session, remediation_id: int) -> None:
    db.execute(
        text("UPDATE governance_alerts SET status = 'resolved', resolved_at = :now WHERE alert_key = :key AND status <> 'resolved'"),
        {"now": _now(), "key": _alert_key(remediation_id)},
    )


def _notify(db: Session, item: dict[str, Any]) -> int:
    from app.services import notifications
    from app.services.policies import _guardian_emails

    config = notifications.settings(db)
    if not config.get("enabled"):
        return 0
    recipients = _guardian_emails(db, [item["storage_root_id"]]).get(item["storage_root_id"]) or []
    if not recipients:
        return 0
    root = db.execute(text("SELECT name, root_path FROM storage_roots WHERE id = :id"), {"id": item["storage_root_id"]}).mappings().first() or {}
    files = "\n".join(f"- {path}" for path in item.get("paths", [])[:20])
    notifications.queue(
        f"remediation:{item['id']}",
        recipients,
        f"[BornToShare] Mots de passe à retirer : {root.get('name') or root.get('root_path')}",
        f"Des fichiers contenant des mots de passe ont été trouvés dans {root.get('root_path')}.\n"
        f"Merci de les supprimer ou de les déplacer vers un coffre avant le {item['due_at'][:10]}.\n\n{files}\n"
        + (f"\n{item['note']}\n" if item.get("note") else "")
        + "\nLe dossier sera analysé de nouveau à cette date."
        + notifications._link(config, f"/storage-roots?selected={item['storage_root_id']}"),
    )
    return 1


def create(db: Session, storage_root_id: int, *, due_days: int, note: str | None, by: str | None) -> dict[str, Any]:
    paths = password_paths(db, storage_root_id)
    result = db.execute(
        text(
            """
            INSERT INTO sensitivity_remediations (storage_root_id, status, files_at_request, paths_json, note, requested_by, requested_at, due_at)
            VALUES (:id, 'open', :files, :paths, :note, :by, :now, :due)
            """
        ),
        {"id": int(storage_root_id), "files": len(paths), "paths": json.dumps(paths), "note": (note or None) and note[:500],
         "by": by, "now": _now(), "due": _now() + timedelta(days=int(due_days))},
    )
    db.commit()
    item = _row(db.execute(text("SELECT * FROM sensitivity_remediations WHERE id = :id"), {"id": int(result.lastrowid)}).mappings().first())
    _alert(db, item, overdue=False)
    db.commit()
    try:
        item["notified"] = _notify(db, item)
    except Exception:
        logger.warning("REMEDIATION_NOT_NOTIFIED", exc_info=True)
        item["notified"] = 0
    return item


def close(db: Session, remediation_id: int, *, status: str, by: str | None) -> None:
    db.execute(
        text("UPDATE sensitivity_remediations SET status = :status, closed_at = :now, closed_by = :by WHERE id = :id AND status IN ('open', 'overdue')"),
        {"id": int(remediation_id), "status": status, "now": _now(), "by": by},
    )
    _resolve_alert(db, remediation_id)
    db.commit()


def after_scan(db: Session, storage_root_id: int) -> str | None:
    """A scan of the folder landed: done when no password file is left, overdue when still there after the due date."""
    item = current(db, storage_root_id)
    if not item:
        return None
    if not password_paths(db, storage_root_id):
        close(db, item["id"], status="done", by="scan")
        return "done"
    due = datetime.fromisoformat(item["due_at"][:-1]) if item.get("due_at") else None
    if due and due <= _now() and item["status"] != "overdue":
        db.execute(text("UPDATE sensitivity_remediations SET status = 'overdue' WHERE id = :id"), {"id": item["id"]})
        _alert(db, {**item, "status": "overdue"}, overdue=True)
        db.commit()
        return "overdue"
    return item["status"]


def due_for_rescan(db: Session) -> list[int]:
    """Open corrections past their due date whose folder was not scanned again yet: their folders."""
    rows = db.execute(
        text("SELECT id, storage_root_id FROM sensitivity_remediations WHERE status = 'open' AND due_at <= :now AND rescan_requested_at IS NULL"),
        {"now": _now()},
    ).all()
    if rows:
        db.execute(text("UPDATE sensitivity_remediations SET rescan_requested_at = :now WHERE id IN :ids")
                   .bindparams(bindparam("ids", expanding=True)),
                   {"now": _now(), "ids": [int(row[0]) for row in rows]})
        db.commit()
    return sorted({int(row[1]) for row in rows})


def counts_by_root(db: Session, storage_root_ids: list[int]) -> dict[int, str]:
    """Open correction per folder (open | overdue), for the list and the 5S."""
    ids = sorted({int(value) for value in storage_root_ids if int(value) > 0})
    if not ids:
        return {}
    try:
        rows = db.execute(
            text("SELECT storage_root_id, MAX(status = 'overdue') FROM sensitivity_remediations WHERE status IN ('open', 'overdue') "
                 "AND storage_root_id IN :ids GROUP BY storage_root_id").bindparams(bindparam("ids", expanding=True)),
            {"ids": ids},
        ).all()
    except Exception:
        db.rollback()
        return {}
    return {int(root_id): ("overdue" if overdue else "open") for root_id, overdue in rows}
