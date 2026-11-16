"""The monthly report of BornToShare (Settings › Notifications): what the governance did in the month (requests,
decisions, revocations, accesses in force, alerts, access reviews) and, when the 5S module is active, what it found
(volume and growth, duplicates, old data, 5S score, quarantine). Sent to the administrators on the 1st of each month
for the month before (switched on in the settings), or at once from the settings (preview, test)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("core.monthly_report")
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def previous_month(today: datetime | None = None) -> tuple[datetime, datetime, str]:
    """(first day, first day of the next month, « octobre 2026 ») of the month before `today`."""
    day = (today or _now()).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = (day - timedelta(days=1)).replace(day=1)
    return start, day, f"{MONTHS[start.month - 1]} {start.year}"


def _one(db: Session, sql: str, params: dict[str, Any]) -> int:
    try:
        return int(db.execute(text(sql), params).scalar() or 0)
    except Exception:
        db.rollback()
        return 0


def build(db: Session, since: datetime, until: datetime) -> dict[str, Any]:
    """The figures of the period."""
    from app.services import features, modules

    window = {"since": since, "until": until}
    governance = {
        "requests": _one(db, "SELECT COUNT(*) FROM access_requests WHERE created_at >= :since AND created_at < :until", window),
        "approved": _one(db, """SELECT COUNT(*) FROM access_requests WHERE decided_at >= :since AND decided_at < :until
                                AND LOWER(status) IN ('approved', 'applied', 'active', 'executed', 'revoked', 'expired')""", window),
        "rejected": _one(db, "SELECT COUNT(*) FROM access_requests WHERE decided_at >= :since AND decided_at < :until AND LOWER(status) = 'rejected'", window),
        "revoked": _one(db, "SELECT COUNT(*) FROM access_requests WHERE revoked_at >= :since AND revoked_at < :until", window),
        "active": _one(db, "SELECT COUNT(*) FROM access_requests WHERE LOWER(status) IN ('approved', 'applied', 'active', 'executed')", {}),
        "alerts_open": _one(db, "SELECT COUNT(*) FROM governance_alerts WHERE LOWER(status) = 'open'", {}),
        "alerts_critical": _one(db, "SELECT COUNT(*) FROM governance_alerts WHERE LOWER(status) = 'open' AND LOWER(severity) IN ('critical', 'high')", {}),
        "folders": _one(db, "SELECT COUNT(*) FROM storage_roots", {}),
    }
    reviews = {
        "open": _one(db, "SELECT COUNT(*) FROM access_reviews WHERE status = 'open'", {}),
        "decided": _one(db, """SELECT COUNT(*) FROM access_review_items i JOIN access_reviews r ON r.id = i.review_id
                               WHERE i.decided_at >= :since AND i.decided_at < :until""", window),
        "removed": _one(db, """SELECT COUNT(*) FROM access_review_items WHERE decision = 'revoke' AND decided_at >= :since AND decided_at < :until""", window),
        "waiting": _one(db, """SELECT COUNT(*) FROM access_review_items i JOIN access_reviews r ON r.id = i.review_id
                               WHERE r.status = 'open' AND i.decision IS NULL""", {}),
    }
    fives = None
    if features.enabled(db, "fives") and modules.fives_url():
        fives = modules.fives_summary(since)
    return {"since": since.isoformat() + "Z", "until": until.isoformat() + "Z", "governance": governance, "reviews": reviews, "fives": fives}


def _size(value: int | None) -> str:
    size = float(value or 0)
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if abs(size) < 1024 or unit == "To":
            return f"{size:.1f} {unit}".replace(".0 ", " ").replace(".", ",")
        size /= 1024
    return str(value)


def lines(data: dict[str, Any]) -> list[tuple[str, list[tuple[str, str]]]]:
    """The report as sections of (label, value): the same text for the mail and its preview."""
    g, r, f = data["governance"], data["reviews"], data.get("fives")
    sections = [
        ("Accès", [("Demandes reçues", str(g["requests"])), ("Accordées", str(g["approved"])), ("Refusées", str(g["rejected"])),
                   ("Retirées", str(g["revoked"])), ("Accès en vigueur", str(g["active"]))]),
        ("Revue des accès", [("Campagnes ouvertes", str(r["open"])), ("Accès revus dans le mois", str(r["decided"])),
                             ("Retraits décidés", str(r["removed"])), ("Encore à revoir", str(r["waiting"]))]),
        ("Alertes", [("Ouvertes", str(g["alerts_open"])), ("Critiques ou hautes", str(g["alerts_critical"])), ("Dossiers gouvernés", str(g["folders"]))]),
    ]
    if f:
        sections.append(("Stockage (module 5S)", [
            ("Volume mesuré", f"{_size(f.get('bytes'))} ({f.get('folders_measured', 0)} dossier(s))"),
            ("Croissance du mois", ("+" if (f.get("growth_bytes") or 0) >= 0 else "") + _size(f.get("growth_bytes"))),
            ("Perdu en doublons", _size(f.get("duplicate_bytes"))), ("Non modifié depuis 3 ans", _size(f.get("cold_3y_bytes"))),
            ("Score 5S moyen", f"{f['score']} / 100" if f.get("score") is not None else "—"),
            ("Mis en quarantaine", f"{(f.get('quarantined') or {}).get('files', 0)} copie(s), {_size((f.get('quarantined') or {}).get('bytes'))}"),
            ("Dossiers archivés", str(f.get("archived", 0))), ("Mesures partielles", str(f.get("partial_measures", 0))),
        ]))
    return sections


def send(db: Session, *, since: datetime, until: datetime, label: str, key: str, recipients: list[str] | None = None) -> dict[str, Any]:
    """Build and queue the report (once per key). Returns the figures and who it went to."""
    from app.services import mail_templates as mt
    from app.services import notifications

    data = build(db, since, until)
    config = notifications.settings(db)
    to = recipients if recipients is not None else notifications._admin_emails(db)
    sections = lines(data)
    url = notifications._url(config, "/dashboard")
    html = mt.layout(
        preheader=f"Le mois de {label} dans BornToShare", eyebrow="Rapport mensuel", title=f"BornToShare en {label}",
        intro="Ce que la gouvernance a fait dans le mois, et ce qui attend encore.",
        blocks=[mt.heading(title) + mt.details((name, mt.e(value)) for name, value in rows) for title, rows in sections],
        buttons=[mt.button("Ouvrir BornToShare", url)] if url else [],
        footer="Vous recevez ce rapport une fois par mois parce que vous êtes administrateur de BornToShare (Settings › Notifications).",
    )
    body = "\n\n".join(f"{title}\n" + "\n".join(f"- {name} : {value}" for name, value in rows) for title, rows in sections)
    if config.get("enabled") and to:
        notifications.queue(key, to, f"[BornToShare] Rapport de {label}", f"BornToShare en {label}\n\n{body}" + notifications._link(config, "/dashboard"), html)
    return {"label": label, "recipients": to if config.get("enabled") else [], "mail_enabled": bool(config.get("enabled")), "sections": sections, "data": data}


def maybe_send(db: Session, today: datetime | None = None) -> bool:
    """On the 1st of the month, the report of the month before, once (key monthly_report:YYYY-MM), when switched on."""
    from app.services import notifications

    now = today or _now()
    config = notifications.settings(db)
    if now.day != 1 or not config.get("enabled") or not config.get("monthlyReport"):
        return False
    since, until, label = previous_month(now)
    key = f"monthly_report:{since:%Y-%m}"
    if notifications._already_sent(db, key):
        return False
    try:
        send(db, since=since, until=until, label=label, key=key)
        return True
    except Exception:
        db.rollback()
        logger.warning("MONTHLY_REPORT_FAILED", exc_info=True)
        return False
