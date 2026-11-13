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


def send_mail(config: dict[str, Any], password: str | None, recipients: list[str], subject: str, body: str, html: str | None = None) -> None:
    host = str(config.get("host") or "").strip()
    port = int(config.get("port") or 587)
    security = str(config.get("security") or "starttls")
    message = EmailMessage()
    message["From"] = str(config.get("sender") or "")
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)
    if html:
        # The text stays for the clients that do not show HTML
        message.add_alternative(html, subtype="html")
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


def _deliver(key: str, recipients: list[str], subject: str, body: str, html: str | None = None) -> None:
    from app.core.db import SessionLocal
    from app.services.secret_store import resolve

    db = SessionLocal()
    try:
        config = settings(db)
        if not config.get("enabled") or not recipients or _already_sent(db, key):
            return
        password = resolve(db, config["passwordRef"]) if config.get("passwordRef") else None
        try:
            send_mail(config, password, recipients, subject, body, html)
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


def queue(key: str, recipients: list[str], subject: str, body: str, html: str | None = None) -> None:
    """Never blocks nor fails the caller."""
    clean = sorted({r.strip() for r in recipients if r and "@" in r})
    if clean:
        _executor.submit(_deliver, key, clean, subject, body, html)


def _link(config: dict[str, Any], path: str) -> str:
    base = str(config.get("appUrl") or "").rstrip("/")
    return f"\n\n{base}{path}" if base else ""


def _url(config: dict[str, Any], path: str) -> str:
    base = str(config.get("appUrl") or "").rstrip("/")
    return f"{base}{path}" if base else ""


def _level(permission: Any) -> tuple[str, str]:
    write = str(permission or "").upper().startswith("W")
    return ("Modifier", "créer, changer et supprimer des fichiers") if write else ("Lire", "ouvrir et copier les fichiers")


def _duration(expires_at: Any) -> str:
    from app.services.mail_templates import long_date

    return f"jusqu'au {long_date(expires_at)}, retiré automatiquement ce jour-là" if expires_at else "Permanent"


def _request(db: Session, request_id: int) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT ar.id, ar.code, ar.status, ar.justification, ar.decision_comment, ar.requester_identity_id,
                   req.email AS requester_email, COALESCE(req.display_name, req.username) AS requester,
                   ar.created_at, ar.decided_at, ari.permission, ari.expires_at, sr.id AS root_id, sr.name AS root_name,
                   sr.root_path
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


def _bell_request_created(db: Session, request_id: int) -> None:
    from app.services import inbox

    row = _request(db, request_id)
    if not row or not row["root_id"]:
        return
    verb, _meaning = _level(row["permission"])
    inbox.push(db, inbox.guardians_of(db, int(row["root_id"])), f"request:{row['id']}:created", kind="request", severity="warning",
               title=f"{row['requester']} demande à {verb.lower()} « {row['root_name']} »",
               body=row["justification"] or None, link=f"/access-requests?status=pending&focus={row['id']}")


def request_created(db: Session, request_id: int) -> None:
    try:
        _bell_request_created(db, request_id)
    except Exception:
        logger.warning("INBOX_REQUEST_FAILED", exc_info=True)
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
                    UNION
                    -- The backup guardians in force are told as well
                    SELECT s.email FROM storage_root_roles srr
                    JOIN guardian_substitutes gs ON gs.identity_id = srr.identity_id AND gs.revoked_at IS NULL
                      AND gs.starts_at <= UTC_TIMESTAMP() AND gs.ends_at > UTC_TIMESTAMP()
                    JOIN identities s ON s.id = gs.substitute_identity_id AND s.is_active = 1
                    WHERE srr.root_id = :root AND LOWER(srr.role) = 'guardian' AND s.email IS NOT NULL
                    """
                ),
                {"root": int(row["root_id"])},
            )
        ]
        from app.services import mail_templates as mt

        level = "modification" if str(row["permission"] or "").upper().startswith("W") else "lecture"
        verb, meaning = _level(row["permission"])
        url = _url(config, f"/access-requests?status=pending&focus={row['id']}")
        html = mt.layout(
            preheader=f"{row['requester']} demande à {verb.lower()} le dossier {row['root_name']}",
            eyebrow="Nouvelle demande d'accès",
            title=f"{row['requester']} demande à {verb.lower()} le dossier « {row['root_name']} »",
            intro="Vous êtes gardien de ce dossier : votre décision suffit.",
            blocks=[
                mt.details([
                    ("Dossier", f"<strong>{mt.e(row['root_name'])}</strong><br>{mt.code(row.get('root_path') or '')}"),
                    ("Niveau", f"<strong>{mt.e(verb)}</strong> <span style=\"color:{mt.MUTED}\">· {mt.e(meaning)}</span>"),
                    ("Durée", mt.e(_duration(row["expires_at"]))),
                ]),
                mt.quote("Motif", row["justification"] or "—"),
            ],
            buttons=[mt.button("Voir la demande", url)] if url else [],
            footer=f"Vous recevez ce mail parce que vous êtes gardien du dossier {row['root_name']}.",
            badge=row.get("code") or f"REQ-{row['id']}",
        )
        queue(
            f"request:{row['id']}:created",
            guardians,
            f"[BornToShare] Demande d'accès à {row['root_name']} : votre décision est attendue",
            f"{row['requester']} demande un accès en {level} au dossier {row['root_name']}.\n\nMotif : {row['justification'] or '—'}"
            + _link(config, f"/access-requests?status=pending&focus={row['id']}"),
            html,
        )
    except Exception:
        logger.warning("NOTIFICATION_REQUEST_FAILED", exc_info=True)


def _bell_request_decided(db: Session, request_id: int, decision: str) -> None:
    from app.services import inbox

    row = _request(db, request_id)
    if not row or not row.get("requester_identity_id"):
        return
    accepted = decision in {"approved", "approve"}
    inbox.push(db, [row["requester_identity_id"]], f"request:{row['id']}:{decision}", kind="decision", severity="success" if accepted else "danger",
               title=(f"Votre accès à « {row['root_name']} » est accordé" if accepted else f"Votre demande d'accès à « {row['root_name']} » est refusée"),
               body=row.get("decision_comment") or None, link=f"/access-requests?focus={row['id']}")


def request_decided(db: Session, request_id: int, decision: str) -> None:
    try:
        _bell_request_decided(db, request_id, decision)
    except Exception:
        logger.warning("INBOX_DECISION_FAILED", exc_info=True)
    try:
        config = settings(db)
        if not config.get("enabled") or not config.get("decisionToRequester"):
            return
        row = _request(db, request_id)
        if not row:
            return
        from app.services import mail_templates as mt

        accepted = decision in {"approved", "approve"}
        comment = f"\n\nCommentaire du gardien : {row['decision_comment']}" if row.get("decision_comment") else ""
        verb, _meaning = _level(row["permission"])
        url = _url(config, f"/access-requests?focus={row['id']}")
        blocks = []
        if accepted:
            blocks.append(mt.details([("Niveau", f"<strong>{mt.e(verb)}</strong>"), ("Durée", mt.e(_duration(row["expires_at"])))]))
        if row.get("decision_comment"):
            blocks.append(mt.quote("Le mot du gardien", row["decision_comment"]))
        if accepted and row.get("root_path"):
            blocks.append(mt.dark_box("Ouvrir le dossier", row["root_path"],
                                      "Collez ce chemin dans l'Explorateur. Le dossier n'apparaît pas ? Fermez votre session Windows puis "
                                      "rouvrez-la : vos nouveaux droits sont lus à la connexion."))
        html = mt.layout(
            preheader=f"Votre demande d'accès à {row['root_name']} est {'acceptée' if accepted else 'refusée'}",
            eyebrow="Accès accordé" if accepted else "Demande refusée",
            title=(f"Votre accès au dossier « {row['root_name']} » est accordé" if accepted
                   else f"Votre demande d'accès au dossier « {row['root_name']} » est refusée"),
            intro=("Il est mis en place sur le serveur de fichiers : il est effectif en quelques minutes." if accepted
                   else "Le gardien du dossier n'a pas accepté cette demande. Vous pouvez en faire une nouvelle, avec plus de précisions."),
            blocks=blocks,
            buttons=[mt.button("Voir mes demandes", url)] if url else [],
            footer="Vous recevez ce mail parce que vous avez demandé cet accès.",
            badge=row.get("code") or f"REQ-{row['id']}",
        )
        queue(
            f"request:{row['id']}:{decision}",
            [row["requester_email"]],
            f"[BornToShare] Votre demande d'accès à {row['root_name']} est {'acceptée' if accepted else 'refusée'}",
            ("Votre accès est en cours de mise en place : il est effectif en quelques minutes." if accepted else "Votre demande a été refusée.")
            + comment
            + _link(config, f"/access-requests?focus={row['id']}"),
            html,
        )
    except Exception:
        logger.warning("NOTIFICATION_DECISION_FAILED", exc_info=True)


def _admin_emails(db: Session) -> list[str]:
    """The platform administrators who have an address."""
    try:
        rows = db.execute(text("""
            SELECT DISTINCT i.email FROM v_identity_effective_roles r JOIN identities i ON i.id = r.identity_id
            WHERE r.role_code = 'platform_admin' AND i.is_active = 1 AND i.email IS NOT NULL AND i.email <> ''""")).all()
    except Exception:
        db.rollback()
        return []
    return [str(row[0]) for row in rows]


def admin_alert(db: Session, key: str, title: str, lines: list[str], path: str, *, intro: str) -> None:
    """A breakdown of the platform (server unreachable, component down) told to the administrators, once per key.
    Never blocks nor fails the caller."""
    try:
        from app.services import inbox

        inbox.push(db, inbox.admins(db), key, kind="alert", severity="danger", title=title, body="\n".join([intro, *lines[:4]]), link=path)
    except Exception:
        logger.warning("INBOX_ADMIN_ALERT_FAILED", exc_info=True)
    try:
        config = settings(db)
        if not config.get("enabled") or not config.get("adminAlerts", True):
            return
        recipients = _admin_emails(db)
        if not recipients:
            return
        from app.services import mail_templates as mt

        url = _url(config, path)
        html = mt.layout(
            preheader=title, eyebrow="Infrastructure", title=title, intro=intro, alert=True, badge="Panne",
            blocks=[mt.notice("Constaté", "<br>".join(mt.e(line) for line in lines[:12]),
                              "Une seule alerte par panne ; elle se ferme d'elle-même au premier contrôle réussi.")],
            buttons=[mt.button("Ouvrir l'observabilité", url)] if url else [],
            footer="Vous recevez ce mail parce que vous êtes administrateur de BornToShare.",
        )
        queue(key, recipients, f"[BornToShare] {title}", "\n".join([intro, "", *lines]) + _link(config, path), html)
    except Exception:
        logger.warning("NOTIFICATION_ADMIN_ALERT_FAILED", exc_info=True)


def expiry_reminders(db: Session) -> int:
    """Accesses that end within the reminder days, told once to their holder. Returns how many were queued."""
    config = settings(db)
    days = int(config.get("expiryReminderDays") or 0)
    if days <= 0:
        return 0
    # The bell tells every holder; the mail goes only when it is switched on and the holder has an address
    mail_on = bool(config.get("enabled"))
    rows = db.execute(
        text(
            """
            SELECT ar.id, ar.code, ari.expires_at, ari.permission, COALESCE(ar.decided_at, ar.created_at) AS since,
                   req.email, ar.requester_identity_id, sr.name AS root_name, sr.root_path
            FROM access_requests ar
            JOIN access_request_items ari ON ari.access_request_id = ar.id
            JOIN identities req ON req.id = ar.requester_identity_id
            JOIN storage_roots sr ON sr.id = ari.target_id
            WHERE LOWER(ar.status) IN ('approved', 'applied', 'active')
              AND ari.expires_at IS NOT NULL
              AND ari.expires_at BETWEEN NOW() AND NOW() + INTERVAL :days DAY
            """
        ),
        {"days": days},
    ).mappings().all()
    from datetime import datetime as _dt

    from app.services import mail_templates as mt

    from app.services import inbox

    now = _dt.utcnow()
    queued = 0
    for row in rows:
        verb, _meaning = _level(row["permission"])
        inbox.push(db, [row["requester_identity_id"]], f"request:{row['id']}:expiry", kind="expiry", severity="warning",
                   title=f"Votre accès à « {row['root_name']} » se termine le {row['expires_at']:%d/%m/%Y}",
                   body="Vos droits seront retirés automatiquement ce jour-là. Besoin de plus de temps ? Faites une nouvelle demande.",
                   link=f"/access-requests?focus={row['id']}")
        if not mail_on or not row.get("email"):
            continue
        queued += 1
        left = max(0, (row["expires_at"] - now).days)
        total = (row["expires_at"] - row["since"]).total_seconds() if row.get("since") else 0
        used = (now - row["since"]).total_seconds() if row.get("since") else 0
        url = _url(config, f"/access-requests?focus={row['id']}")
        html = mt.layout(
            preheader=f"Votre accès à {row['root_name']} se termine le {mt.long_date(row['expires_at'])}",
            eyebrow="Rappel",
            title=(f"Votre accès au dossier « {row['root_name']} » se termine dans {left} jour{'s' if left > 1 else ''}" if left
                   else f"Votre accès au dossier « {row['root_name']} » se termine aujourd'hui"),
            intro="Ce jour-là, vos droits seront retirés automatiquement. Les fichiers restent dans le dossier.",
            blocks=[mt.date_block(row["expires_at"], f"{row['root_name']} · {verb}", row.get("root_path") or "",
                                  (used / total) if total > 0 else None,
                                  f"{int(used // 86400)} jours sur {int(total // 86400)} utilisés" if total > 0 else "")],
            buttons=[b for b in ([mt.button("Voir mon accès", url)] if url else [])]
            + ([mt.button("Faire une nouvelle demande", _url(config, "/access-requests/new"), primary=False)] if url else []),
            footer="Vous recevez ce rappel une seule fois avant la fin de votre accès. Rien à faire si vous n'en avez plus besoin.",
            badge=row.get("code") or f"REQ-{row['id']}",
        )
        queue(
            f"request:{row['id']}:expiry",
            [row["email"]],
            f"[BornToShare] Votre accès à {row['root_name']} se termine le {row['expires_at']:%d/%m/%Y}",
            f"Votre accès au dossier {row['root_name']} sera retiré automatiquement le {row['expires_at']:%d/%m/%Y}.\n"
            "Si vous en avez encore besoin, faites une nouvelle demande avant cette date."
            + _link(config, "/access-requests/new"),
            html,
        )
    return queued
