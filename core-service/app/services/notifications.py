"""E-mails of BornToShare (Advanced Settings › Notifications), sent in the background through the SMTP server set there.

- a new access request: its guardians
- a decision: the requester
- an access that ends in N days: the person who has it (once, during the access expiry run)

Each message has a key written to notification_log: the same notice is never sent twice.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="b2s-mail")


def settings(db: Session) -> dict[str, Any]:
    from app.api.advanced_settings import _read_payload

    return dict(_read_payload(db).get("notifications") or {})


def send_mail(config: dict[str, Any], password: str | None, recipients: list[str], subject: str, body: str) -> None:
    host = str(config.get("host") or "").strip()
    port = int(config.get("port") or 587)
    security = str(config.get("security") or "starttls")
    message = EmailMessage()
    message["From"] = str(config.get("sender") or "")
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)
    context = ssl.create_default_context()
    if security == "tls":
        client: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
    else:
        client = smtplib.SMTP(host, port, timeout=15)
    with client:
        if security == "starttls":
            client.starttls(context=context)
        if config.get("username") and password:
            client.login(str(config["username"]), password)
        client.send_message(message)


def _already_sent(db: Session, key: str) -> bool:
    try:
        return db.execute(text("SELECT 1 FROM notification_log WHERE notice_key = :key AND status = 'sent'"), {"key": key}).first() is not None
    except Exception:  # table not created yet (pack 148)
        db.rollback()
        return True


def _deliver(key: str, recipients: list[str], subject: str, body: str) -> None:
    from app.core.db import SessionLocal
    from app.services.secret_store import resolve

    db = SessionLocal()
    try:
        config = settings(db)
        if not config.get("enabled") or not recipients or _already_sent(db, key):
            return
        password = resolve(db, config["passwordRef"]) if config.get("passwordRef") else None
        try:
            send_mail(config, password, recipients, subject, body)
            status, detail = "sent", None
        except Exception as exc:
            status, detail = "failed", str(exc)[:300]
        db.execute(
            text(
                """
                INSERT INTO notification_log (notice_key, recipients, status, detail) VALUES (:key, :to, :status, :detail)
                ON DUPLICATE KEY UPDATE status = VALUES(status), detail = VALUES(detail), sent_at = CURRENT_TIMESTAMP
                """
            ),
            {"key": key[:190], "to": ", ".join(recipients)[:500], "status": status, "detail": detail},
        )
        db.commit()
    except Exception:
        logger.warning("NOTIFICATION_FAILED", exc_info=True)
    finally:
        db.close()


def queue(key: str, recipients: list[str], subject: str, body: str) -> None:
    """Never blocks nor fails the caller."""
    clean = sorted({r.strip() for r in recipients if r and "@" in r})
    if clean:
        _executor.submit(_deliver, key, clean, subject, body)


def _link(config: dict[str, Any], path: str) -> str:
    base = str(config.get("appUrl") or "").rstrip("/")
    return f"\n\n{base}{path}" if base else ""


def _request(db: Session, request_id: int) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT ar.id, ar.code, ar.status, ar.justification, ar.decision_comment, ar.requester_identity_id,
                   req.email AS requester_email, COALESCE(req.display_name, req.username) AS requester,
                   ari.permission, ari.expires_at, sr.id AS root_id, sr.name AS root_name
            FROM access_requests ar
            LEFT JOIN identities req ON req.id = ar.requester_identity_id
            LEFT JOIN access_request_items ari ON ari.access_request_id = ar.id
            LEFT JOIN storage_roots sr ON sr.id = ari.target_id
            WHERE ar.id = :id
            ORDER BY ari.id
            LIMIT 1
            """
        ),
        {"id": int(request_id)},
    ).mappings().first()
    return dict(row) if row else None


def request_created(db: Session, request_id: int) -> None:
    try:
        config = settings(db)
        if not config.get("enabled") or not config.get("pendingToGuardians"):
            return
        row = _request(db, request_id)
        if not row or not row["root_id"]:
            return
        guardians = [
            r[0]
            for r in db.execute(
                text(
                    """
                    SELECT i.email FROM storage_root_roles srr JOIN identities i ON i.id = srr.identity_id
                    WHERE srr.root_id = :root AND LOWER(srr.role) = 'guardian' AND i.email IS NOT NULL
                    """
                ),
                {"root": int(row["root_id"])},
            )
        ]
        level = "modification" if str(row["permission"] or "").upper().startswith("W") else "lecture"
        queue(
            f"request:{row['id']}:created",
            guardians,
            f"[BornToShare] Demande d'accès à {row['root_name']} : votre décision est attendue",
            f"{row['requester']} demande un accès en {level} au dossier {row['root_name']}.\n\nMotif : {row['justification'] or '—'}"
            + _link(config, f"/access-requests?status=pending&focus={row['id']}"),
        )
    except Exception:
        logger.warning("NOTIFICATION_REQUEST_FAILED", exc_info=True)


def request_decided(db: Session, request_id: int, decision: str) -> None:
    try:
        config = settings(db)
        if not config.get("enabled") or not config.get("decisionToRequester"):
            return
        row = _request(db, request_id)
        if not row:
            return
        accepted = decision in {"approved", "approve"}
        comment = f"\n\nCommentaire du gardien : {row['decision_comment']}" if row.get("decision_comment") else ""
        queue(
            f"request:{row['id']}:{decision}",
            [row["requester_email"]],
            f"[BornToShare] Votre demande d'accès à {row['root_name']} est {'acceptée' if accepted else 'refusée'}",
            ("Votre accès est en cours de mise en place : il est effectif en quelques minutes." if accepted else "Votre demande a été refusée.")
            + comment
            + _link(config, f"/access-requests?focus={row['id']}"),
        )
    except Exception:
        logger.warning("NOTIFICATION_DECISION_FAILED", exc_info=True)


def expiry_reminders(db: Session) -> int:
    """Accesses that end within the reminder days, told once to their holder. Returns how many were queued."""
    config = settings(db)
    days = int(config.get("expiryReminderDays") or 0)
    if not config.get("enabled") or days <= 0:
        return 0
    rows = db.execute(
        text(
            """
            SELECT ar.id, ari.expires_at, req.email, sr.name AS root_name
            FROM access_requests ar
            JOIN access_request_items ari ON ari.access_request_id = ar.id
            JOIN identities req ON req.id = ar.requester_identity_id
            JOIN storage_roots sr ON sr.id = ari.target_id
            WHERE LOWER(ar.status) IN ('approved', 'applied', 'active')
              AND ari.expires_at IS NOT NULL
              AND ari.expires_at BETWEEN NOW() AND NOW() + INTERVAL :days DAY
              AND req.email IS NOT NULL
            """
        ),
        {"days": days},
    ).mappings().all()
    for row in rows:
        queue(
            f"request:{row['id']}:expiry",
            [row["email"]],
            f"[BornToShare] Votre accès à {row['root_name']} se termine le {row['expires_at']:%d/%m/%Y}",
            f"Votre accès au dossier {row['root_name']} sera retiré automatiquement le {row['expires_at']:%d/%m/%Y}.\n"
            "Si vous en avez encore besoin, faites une nouvelle demande avant cette date."
            + _link(config, "/access-requests/new"),
        )
    return len(rows)
