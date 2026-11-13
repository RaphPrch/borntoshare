"""Notification centre of the app (the bell): what concerns a person, kept in the database for them.

Written where the e-mails are decided (new request, decision, end of access, platform breakdown) but independent
from them: the bell works with the mail switched off or without an address. One row per person and notice key, so
a notice is never shown twice. Never blocks nor fails the caller.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

KINDS = {"request", "decision", "expiry", "alert", "task"}
SEVERITIES = {"info", "success", "warning", "danger"}


def push(db: Session, identity_ids: Iterable[Any], key: str, *, kind: str, title: str,
         body: str | None = None, link: str | None = None, severity: str = "info") -> int:
    """Adds the notice for each person (once per key). Returns how many rows were new."""
    ids = sorted({int(value) for value in identity_ids if str(value or "").strip().isdigit() and int(value) > 0})
    if not ids:
        return 0
    added = 0
    try:
        for identity_id in ids:
            result = db.execute(
                text(
                    """
                    INSERT IGNORE INTO user_notifications (identity_id, notice_key, kind, severity, title, body, link)
                    VALUES (:identity, :key, :kind, :severity, :title, :body, :link)
                    """
                ),
                {
                    "identity": identity_id, "key": key[:190], "kind": kind if kind in KINDS else "alert",
                    "severity": severity if severity in SEVERITIES else "info",
                    "title": title[:300], "body": (body or None) and body[:600], "link": (link or None) and link[:300],
                },
            )
            added += int(result.rowcount or 0)
        db.commit()
    except Exception:  # table not created yet (pack 161), or a lost connection: the caller goes on
        db.rollback()
        logger.warning("INBOX_PUSH_FAILED", exc_info=True)
    return added


def guardians_of(db: Session, root_id: int) -> list[int]:
    """The guardians of a folder and their backups in force; nobody guards it: the administrators."""
    try:
        rows = db.execute(
            text(
                """
                SELECT srr.identity_id FROM storage_root_roles srr
                WHERE srr.root_id = :root AND LOWER(srr.role) = 'guardian'
                UNION
                SELECT gs.substitute_identity_id FROM storage_root_roles srr
                JOIN guardian_substitutes gs ON gs.identity_id = srr.identity_id AND gs.revoked_at IS NULL
                  AND gs.starts_at <= UTC_TIMESTAMP() AND gs.ends_at > UTC_TIMESTAMP()
                WHERE srr.root_id = :root AND LOWER(srr.role) = 'guardian'
                """
            ),
            {"root": int(root_id)},
        ).all()
    except Exception:
        db.rollback()
        rows = []
    return [int(row[0]) for row in rows if row[0]] or admins(db)


def admins(db: Session) -> list[int]:
    try:
        rows = db.execute(text(
            "SELECT DISTINCT r.identity_id FROM v_identity_effective_roles r JOIN identities i ON i.id = r.identity_id "
            "WHERE r.role_code = 'platform_admin' AND i.is_active = 1")).all()
    except Exception:
        db.rollback()
        return []
    return [int(row[0]) for row in rows if row[0]]


def listing(db: Session, identity_id: int, *, limit: int = 50) -> dict[str, Any]:
    try:
        rows = db.execute(
            text(
                """
                SELECT id, kind, severity, title, body, link, created_at, read_at FROM user_notifications
                WHERE identity_id = :identity ORDER BY id DESC LIMIT :limit
                """
            ),
            {"identity": int(identity_id), "limit": max(1, min(int(limit), 200))},
        ).mappings().all()
        unread = db.execute(
            text("SELECT COUNT(*) FROM user_notifications WHERE identity_id = :identity AND read_at IS NULL"),
            {"identity": int(identity_id)},
        ).scalar()
    except Exception:
        db.rollback()
        return {"items": [], "unread": 0}
    return {"items": [dict(row) for row in rows], "unread": int(unread or 0)}


def mark_read(db: Session, identity_id: int, ids: list[int] | None) -> int:
    """Marks the given notices (all of them when no id is given) as read, for this person only."""
    params: dict[str, Any] = {"identity": int(identity_id)}
    where = "identity_id = :identity AND read_at IS NULL"
    if ids:
        clean = sorted({int(value) for value in ids if int(value) > 0})[:500]
        if not clean:
            return 0
        where += f" AND id IN ({', '.join(f':i{n}' for n in range(len(clean)))})"
        params.update({f"i{n}": value for n, value in enumerate(clean)})
    try:
        result = db.execute(text(f"UPDATE user_notifications SET read_at = UTC_TIMESTAMP() WHERE {where}"), params)
        db.commit()
        return int(result.rowcount or 0)
    except Exception:
        db.rollback()
        return 0


_TASK_TABLES = {"measure": "storage_root_scans", "sensitivity": "storage_root_sensitivity"}


def remember_requester(db: Session, task: str, root_id: int, identity_id: int | None) -> None:
    """The person who asked for this measure or scan of the folder, to tell them when it ends."""
    table = _TASK_TABLES.get(task)
    if not table or not identity_id:
        return
    try:
        db.execute(text(f"UPDATE {table} SET requested_by_identity = :who WHERE storage_root_id = :id"), {"who": int(identity_id), "id": int(root_id)})
        db.commit()
    except Exception:  # column not there yet (pack 161)
        db.rollback()


def tell_requester(db: Session, task: str, root_id: int, *, ok: bool, detail: str | None = None) -> bool:
    """The measure or scan asked by someone ended: a notice to that person, once (the column is cleared). Never raises."""
    table = _TASK_TABLES.get(task)
    if not table:
        return False
    try:
        row = db.execute(
            text(f"SELECT t.requested_by_identity, sr.name FROM {table} t LEFT JOIN storage_roots sr ON sr.id = t.storage_root_id WHERE t.storage_root_id = :id"),
            {"id": int(root_id)},
        ).first()
        if not row or not row[0]:
            return False
        db.execute(text(f"UPDATE {table} SET requested_by_identity = NULL WHERE storage_root_id = :id"), {"id": int(root_id)})
        db.commit()
    except Exception:
        db.rollback()
        return False
    name = row[1] or f"#{root_id}"
    what = "La mesure" if task == "measure" else "Le scan de sensibilité"
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    title = (f"{what} de « {name} » est terminé{'e' if task == 'measure' else ''}" if ok
             else f"{what} de « {name} » a échoué")
    return push(db, [row[0]], f"{task}:{root_id}:{stamp}", kind="task", severity="success" if ok else "danger",
                title=title, body=detail, link=f"/storage-roots?selected={int(root_id)}") > 0


def purge_read(db: Session, days: int = 90) -> int:
    """Notices read more than `days` ago are deleted (unread ones stay, whatever their age). Never raises."""
    try:
        result = db.execute(text("DELETE FROM user_notifications WHERE read_at IS NOT NULL AND read_at < UTC_TIMESTAMP() - INTERVAL :days DAY"),
                            {"days": max(1, int(days))})
        db.commit()
        return int(result.rowcount or 0)
    except Exception:
        db.rollback()
        logger.warning("INBOX_PURGE_FAILED", exc_info=True)
        return 0


def pulse(db: Session, identity_id: int | None, *, admin: bool) -> dict[str, Any]:
    """What changed for this person, cheap enough to be read every few seconds by the live updates of the app:
    unread notices, the latest one, and stamps that move when the requests or the alerts change."""
    out: dict[str, Any] = {"unread": 0, "latest": None, "requests_stamp": None, "alerts_stamp": None, "critical_open": 0}
    try:
        if identity_id:
            row = db.execute(
                text(
                    """
                    SELECT COUNT(*) AS unread, MAX(id) AS latest FROM user_notifications
                    WHERE identity_id = :identity AND read_at IS NULL
                    """
                ),
                {"identity": int(identity_id)},
            ).mappings().first()
            out["unread"] = int((row or {}).get("unread") or 0)
            latest = db.execute(
                text("SELECT id, kind, severity, title, link FROM user_notifications WHERE identity_id = :identity ORDER BY id DESC LIMIT 1"),
                {"identity": int(identity_id)},
            ).mappings().first()
            out["latest"] = dict(latest) if latest else None
        stamp = db.execute(text("SELECT COUNT(*), MAX(COALESCE(updated_at, created_at)) FROM access_requests")).first()
        out["requests_stamp"] = f"{stamp[0]}|{stamp[1]}" if stamp else None
        if admin:
            alerts = db.execute(text(
                "SELECT COUNT(*), MAX(updated_at), SUM(status = 'open' AND severity IN ('critical', 'high')) FROM governance_alerts")).first()
            out["alerts_stamp"] = f"{alerts[0]}|{alerts[1]}" if alerts else None
            out["critical_open"] = int((alerts[2] if alerts else 0) or 0)
    except Exception:
        db.rollback()
        logger.debug("INBOX_PULSE_FAILED", exc_info=True)
    return out
