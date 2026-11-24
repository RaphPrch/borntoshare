"""Deadline of the decisions on access requests (approval SLA).

A pending request is due `decisionDays` days after it was made (Settings › Governance, 3 by default). Every day the
guardians (and their backups in force) who have requests past their due date are reminded, once a day; after
`escalationDays` days (7 by default, 0: never) the administrators are told too, once a day.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.data.repositories.access_requests_views_repo import DEFAULT_DECISION_DAYS

logger = logging.getLogger(__name__)

DEFAULT_ESCALATION_DAYS = 7


def _policy(db: Session) -> dict[str, Any]:
    from app.api.advanced_settings import _read_payload

    try:
        return dict(_read_payload(db).get("requests") or {})
    except Exception:
        db.rollback()
        return {}


def decision_days(db: Session) -> int:
    value = _policy(db).get("decisionDays")
    return int(value) if isinstance(value, int) and value > 0 else DEFAULT_DECISION_DAYS


def escalation_days(db: Session) -> int:
    value = _policy(db).get("escalationDays")
    return int(value) if isinstance(value, int) and value >= 0 else DEFAULT_ESCALATION_DAYS


def _overdue_by_reviewer(db: Session, days: int) -> dict[int, dict[str, Any]]:
    """The people who decide on requests past their due date: the guardians of the folder and their backups in force."""
    rows = db.execute(
        text(
            """
            SELECT reviewer.id AS identity_id, reviewer.email, COUNT(DISTINCT ar.id) AS overdue, MIN(ar.created_at) AS oldest
            FROM access_requests ar
            JOIN access_request_items ari ON ari.access_request_id = ar.id AND ari.target_type = 'storage_root'
            JOIN storage_root_roles srr ON srr.root_id = ari.target_id AND LOWER(srr.role) = 'guardian'
            LEFT JOIN guardian_substitutes gs ON gs.identity_id = srr.identity_id AND gs.revoked_at IS NULL
              AND gs.starts_at <= UTC_TIMESTAMP() AND gs.ends_at > UTC_TIMESTAMP()
            JOIN identities reviewer ON reviewer.id IN (srr.identity_id, gs.substitute_identity_id) AND reviewer.is_active = 1
            WHERE ar.status = 'pending' AND ar.created_at < UTC_TIMESTAMP() - INTERVAL :days DAY
            GROUP BY reviewer.id, reviewer.email
            """
        ),
        {"days": int(days)},
    ).mappings().all()
    return {int(row["identity_id"]): dict(row) for row in rows}


def _escalated(db: Session, days: int) -> list[dict[str, Any]]:
    """Requests pending for more than `days` days, oldest first (what the administrators are told about)."""
    rows = db.execute(
        text(
            """
            SELECT ar.id, ar.code, ar.created_at, sr.name AS root_name
            FROM access_requests ar
            LEFT JOIN access_request_items ari ON ari.access_request_id = ar.id AND ari.target_type = 'storage_root'
            LEFT JOIN storage_roots sr ON sr.id = ari.target_id
            WHERE ar.status = 'pending' AND ar.created_at < UTC_TIMESTAMP() - INTERVAL :days DAY
            ORDER BY ar.created_at
            """
        ),
        {"days": int(days)},
    ).mappings().all()
    seen: dict[int, dict[str, Any]] = {}
    for row in rows:
        seen.setdefault(int(row["id"]), dict(row))
    return list(seen.values())


def overdue_reminders(db: Session) -> dict[str, int]:
    """Run once a day (schedule « access_expiry »): reminds the reviewers, escalates to the administrators."""
    from app.services import inbox, notifications

    today = datetime.now(timezone.utc).date().isoformat()
    days = decision_days(db)
    config = notifications.settings(db)
    mail_on = bool(config.get("enabled")) and bool(config.get("pendingToGuardians", True))
    reminded = 0
    for identity_id, row in _overdue_by_reviewer(db, days).items():
        count = int(row["overdue"] or 0)
        key = f"requests:overdue:{identity_id}:{today}"
        title = f"{count} demande(s) attendent votre décision depuis plus de {days} jour(s)"
        inbox.push(db, [identity_id], key, kind="request", severity="warning", title=title,
                   body="Le demandeur attend : acceptez ou refusez depuis la page des demandes.", link="/access-requests?status=pending&overdue=1")
        reminded += 1
        if mail_on and row.get("email"):
            notifications.queue(key, [row["email"]], f"[BornToShare] {title}",
                                f"{title}.\n\nLe demandeur attend votre décision."
                                + notifications._link(config, "/access-requests?status=pending&overdue=1"))
    escalate = escalation_days(db)
    escalated = _escalated(db, escalate) if escalate > 0 else []
    if escalated:
        key = f"requests:escalated:{today}"
        title = f"{len(escalated)} demande(s) sans décision depuis plus de {escalate} jours"
        lines = [f"{item.get('code') or 'REQ-' + str(item['id'])} · {item.get('root_name') or '—'} · depuis le {item['created_at']:%d/%m/%Y}"
                 for item in escalated[:12]]
        inbox.push(db, inbox.admins(db), key, kind="request", severity="danger", title=title,
                   body="Les gardiens n'ont pas décidé : relancez-les, désignez un suppléant ou décidez vous-même.\n" + "\n".join(lines[:4]),
                   link="/access-requests?status=pending&overdue=1")
        if config.get("enabled"):
            recipients = notifications._admin_emails(db)
            if recipients:
                notifications.queue(key, recipients, f"[BornToShare] {title}",
                                    "\n".join([f"{title}.", "Les gardiens n'ont pas décidé.", "", *lines])
                                    + notifications._link(config, "/access-requests?status=pending&overdue=1"))
    return {"reminded": reminded, "escalated": len(escalated)}
