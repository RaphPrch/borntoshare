from __future__ import annotations

import json
from copy import deepcopy
from json import JSONDecodeError

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.internal_auth import require_internal_token
from app.api._helpers import ui_action, ui_data
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request, admin_only, admin_or_internal

router = APIRouter(prefix="/admin", tags=["advanced-settings"])


# "logging" and "sessions" are read by auth-service, "governance" by core-service; other sections were stored but never applied.
DEFAULT_ADVANCED_SETTINGS: dict = {
    "logging": {
        "level": "INFO",
        "retentionEnabled": True,
        "retentionDays": 180,
    },
    "governance": {},
    "sessions": {
        "ttlSeconds": 8 * 60 * 60,
        "idleSeconds": 30 * 60,
    },
    # DNS servers of the Windows domains, used by the worker (the directories propose theirs)
    "network": {
        "dns": [],
    },
    # New access requests: the durations offered, the permanent access, the longest access, the reason
    "requests": {
        "durations": [7, 30, 90],
        "allowPermanent": True,
        "maxDays": 365,
        "minReasonLength": 10,
    },
    # Accounts that open a folder to everyone, besides Everyone, Users and Domain users (exposure map, alerts)
    "exposure": {
        "broadGroups": [],
        # Administration accounts expected on folders besides the built-in names (a renamed Administrator, CIS)
        "systemAccounts": [],
    },
    # Failed sign-ins before a pause (read by auth-service)
    "signIn": {
        "maxFailuresPerAccount": 5,
        "maxFailuresPerAddress": 50,
        "windowMinutes": 15,
    },
    # Message shown to every user (maintenance, incident)
    "banner": {
        "enabled": False,
        "message": "",
        "tone": "info",
    },
    # E-mails: guardians told of a request, requesters of the decision and of an access about to end
    "notifications": {
        "enabled": False,
        "host": "",
        "port": 587,
        "security": "starttls",
        "sender": "",
        "username": "",
        "passwordRef": None,
        "appUrl": "",
        "pendingToGuardians": True,
        "decisionToRequester": True,
        "adminAlerts": True,
        "expiryReminderDays": 7,
    },
}



DEPRECATED_ADVANCED_SETTINGS_KEYS = {"platform", "discovery", "integrations", "security", "maintenance"}


def _deep_merge(base: dict, patch: dict) -> dict:
    out = deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _sanitize_advanced_settings(payload: dict) -> dict:
    cleaned = deepcopy(payload if isinstance(payload, dict) else {})
    for key in DEPRECATED_ADVANCED_SETTINGS_KEYS:
        cleaned.pop(key, None)
    # The minimum number of guardians per folder is no longer a setting
    if isinstance(cleaned.get("governance"), dict):
        cleaned["governance"].pop("minGuardians", None)
    return cleaned


def _read_payload(db: Session) -> dict:
    row = db.execute(
        text(
            """
            SELECT payload_json
            FROM advanced_settings_config
            WHERE id = 1
            """
        )
    ).mappings().first()

    if not row or row.get("payload_json") is None:
        return deepcopy(DEFAULT_ADVANCED_SETTINGS)

    raw = row.get("payload_json")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            merged = _deep_merge(DEFAULT_ADVANCED_SETTINGS, parsed if isinstance(parsed, dict) else {})
            return _sanitize_advanced_settings(merged)
        except JSONDecodeError:
            return deepcopy(DEFAULT_ADVANCED_SETTINGS)

    if isinstance(raw, dict):
        merged = _deep_merge(DEFAULT_ADVANCED_SETTINGS, raw)
        return _sanitize_advanced_settings(merged)

    return deepcopy(DEFAULT_ADVANCED_SETTINGS)


def _write_payload(db: Session, payload: dict) -> None:
    payload_json = json.dumps(payload, ensure_ascii=False)
    db.execute(
        text(
            """
            INSERT INTO advanced_settings_config (id, payload_json)
            VALUES (1, :payload)
            ON DUPLICATE KEY UPDATE
              payload_json = :payload,
              updated_at = CURRENT_TIMESTAMP
            """
        ),
        {"payload": payload_json},
    )
    db.commit()


def _changed_settings(before: dict, after: dict, prefix: str = "") -> dict:
    changes: dict = {}
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if isinstance(old, dict) and isinstance(new, dict):
            changes.update(_changed_settings(old, new, f"{prefix}{key}."))
        elif old != new:
            changes[f"{prefix}{key}"] = {"from": old, "to": new}
    return changes


def _invalid(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": code, "message": message})


def _is_int(value: object, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _validate_new_sections(db: Session, merged: dict, payload: dict) -> None:
    """Requests, exposure, sign-in, banner and notifications: checked, cleaned; the SMTP password goes to the vault."""
    requests = merged.get("requests") or {}
    durations = sorted({int(d) for d in requests.get("durations") or [] if _is_int(d, 1, 3650)})
    if not durations and not requests.get("allowPermanent"):
        raise _invalid("REQUEST_POLICY_INVALID", "Proposez au moins une durée, ou autorisez l'accès permanent.")
    if not _is_int(requests.get("maxDays"), 1, 3650) or any(d > requests["maxDays"] for d in durations):
        raise _invalid("REQUEST_POLICY_INVALID", "La durée maximale va de 1 à 3650 jours et couvre les durées proposées.")
    if not _is_int(requests.get("minReasonLength"), 1, 500):
        raise _invalid("REQUEST_POLICY_INVALID", "La longueur minimale du motif va de 1 à 500 caractères.")
    merged["requests"] = {**requests, "durations": durations[:6], "allowPermanent": bool(requests.get("allowPermanent"))}

    exposure = merged.get("exposure") or {}
    groups = exposure.get("broadGroups") or []
    accounts = exposure.get("systemAccounts") or []
    merged["exposure"] = {"broadGroups": sorted({str(g).strip() for g in groups if str(g).strip()})[:50],
                          "systemAccounts": sorted({str(a).strip() for a in accounts if str(a).strip()})[:50]}

    sign_in = merged.get("signIn") or {}
    if not (_is_int(sign_in.get("maxFailuresPerAccount"), 3, 50) and _is_int(sign_in.get("maxFailuresPerAddress"), 10, 1000)
            and _is_int(sign_in.get("windowMinutes"), 1, 1440)):
        raise _invalid("SIGN_IN_LIMITS_INVALID", "Échecs par compte : 3 à 50 ; par adresse : 10 à 1000 ; fenêtre : 1 à 1440 minutes.")

    banner = merged.get("banner") or {}
    message = str(banner.get("message") or "").strip()[:300]
    if banner.get("enabled") and not message:
        raise _invalid("BANNER_INVALID", "Le bandeau activé a besoin d'un message.")
    merged["banner"] = {"enabled": bool(banner.get("enabled")), "message": message, "tone": banner.get("tone") if banner.get("tone") in {"info", "warning", "danger"} else "info"}

    notif = merged.get("notifications") or {}
    password = ((payload.get("notifications") or {}).get("password") or "") if isinstance(payload.get("notifications"), dict) else ""
    notif.pop("password", None)
    notif.pop("hasPassword", None)
    if password:
        from app.services.secret_store import store

        notif["passwordRef"] = store(db, "notifications/smtp", str(password))
    if notif.get("enabled") and not (str(notif.get("host") or "").strip() and "@" in str(notif.get("sender") or "")):
        raise _invalid("SMTP_SETTINGS_INVALID", "Le serveur SMTP et l'adresse d'expéditeur sont requis.")
    if not _is_int(notif.get("port"), 1, 65535) or notif.get("security") not in {"starttls", "tls", "none"}:
        raise _invalid("SMTP_SETTINGS_INVALID", "Port de 1 à 65535 ; sécurité STARTTLS, TLS ou aucune.")
    if not _is_int(notif.get("expiryReminderDays"), 0, 60):
        raise _invalid("SMTP_SETTINGS_INVALID", "Le rappel avant la fin va de 0 (aucun) à 60 jours.")
    merged["notifications"] = notif


def public_settings(db: Session) -> dict:
    """What every signed-in user may read: the request policy and the banner."""
    payload = _read_payload(db)
    return {"requests": payload.get("requests"), "banner": payload.get("banner")}


@router.get("/config/advanced", dependencies=[Depends(admin_or_internal)])
def get_advanced_config(db: Session = Depends(get_db)):
    payload = _read_payload(db)
    # The SMTP password never leaves: the page only knows whether one is set
    notif = dict(payload.get("notifications") or {})
    notif["hasPassword"] = bool(notif.pop("passwordRef", None))
    return ui_data({**payload, "notifications": notif})


@router.get("/config/public")
def get_public_config(db: Session = Depends(get_db)):
    """Request policy and banner, for every signed-in user (new request page, banner of the layout)."""
    return ui_data(public_settings(db))


@router.post("/config/advanced", dependencies=[Depends(admin_or_internal)])
def save_advanced_config(payload: dict, request: Request, db: Session = Depends(get_db)):
    from app.services.log_retention import apply_log_level

    current = _read_payload(db)
    merged = _sanitize_advanced_settings(_deep_merge(current, payload if isinstance(payload, dict) else {}))
    for section in ("logging", "governance", "sessions"):
        if not isinstance(merged.get(section), dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "ADVANCED_SETTINGS_INVALID", "message": f"La section {section} est invalide."},
            )
    logging_cfg = merged["logging"]
    if str(logging_cfg.get("level") or "INFO").upper() not in {"DEBUG", "INFO", "WARN", "WARNING", "ERROR"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "LOG_LEVEL_INVALID", "message": "Niveau de journalisation invalide."},
        )
    # A value out of range would become a retention of one day, and the purge would empty the journal
    days = logging_cfg.get("retentionDays", 180)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 3650:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "LOG_RETENTION_INVALID", "message": "La rétention doit être comprise entre 1 et 3650 jours."},
        )
    sessions = merged.get("sessions") or {}
    ttl, idle = sessions.get("ttlSeconds"), sessions.get("idleSeconds")
    if not (isinstance(ttl, int) and isinstance(idle, int) and 15 * 60 <= ttl <= 30 * 24 * 3600 and 60 <= idle <= ttl):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "SESSION_LIMITS_INVALID", "message": "Durée de session : de 15 minutes à 30 jours ; inactivité : d'une minute à la durée de session."},
        )
    from app.services.domain_dns import validate_entries

    network = merged.get("network") if isinstance(merged.get("network"), dict) else {}
    merged["network"] = {**network, "dns": network.get("dns", [])}
    dns_error = validate_entries(merged["network"]["dns"])
    if dns_error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "DNS_SETTINGS_INVALID", "message": dns_error},
        )
    merged["network"]["dns"] = [
        {"domain": str(e["domain"]).strip().lower().strip("."), "servers": [str(s).strip() for s in e["servers"]]}
        for e in merged["network"]["dns"]
    ]
    _validate_new_sections(db, merged, payload if isinstance(payload, dict) else {})
    _write_payload(db, merged)
    from app.services.storage_root_permissions import forget_broad_cache

    forget_broad_cache()
    # The log level applies to core-service right away (auth-service applies it on its side)
    apply_log_level(str((merged.get("logging") or {}).get("level") or "INFO"))
    changes = _changed_settings(current, merged)
    if changes:
        actor = actor_from_request(request)
        log_activity(
            db,
            actor_type="user" if actor.identity_id is not None else "system",
            actor_id=actor.identity_id,
            actor_display=actor.display_name,
            action="advanced_settings.updated",
            outcome="success",
            target_type="advanced_settings",
            target_display="Advanced settings",
            context_json={"changes": changes},
            correlation_id=(request.headers.get("x-request-id") or None),
        )
    return ui_action(message="advanced settings saved")


@router.post("/config/notifications/test", dependencies=[Depends(admin_only)])
def test_notifications(payload: dict, request: Request, db: Session = Depends(get_db)):
    """A test e-mail to the given address, with the saved SMTP settings; the error of the server comes back as is."""
    from app.services.notifications import send_mail, settings
    from app.services.secret_store import resolve

    to = str((payload or {}).get("to") or "").strip()
    if "@" not in to:
        raise _invalid("SMTP_TEST_INVALID", "Adresse de destination invalide.")
    config = settings(db)
    if not str(config.get("host") or "").strip():
        raise _invalid("SMTP_TEST_INVALID", "Enregistrez d'abord le serveur SMTP.")
    try:
        from app.services import mail_templates as mt

        test_html = mt.layout(
            preheader="Les notifications de BornToShare arrivent bien.", eyebrow="E-mail de test",
            title="Les notifications de BornToShare arrivent bien",
            intro="Ce serveur d'envoi fonctionne : les gardiens recevront les nouvelles demandes, les demandeurs les décisions et les rappels.",
            footer="Envoyé depuis Paramètres avancés › Notifications.",
        )
        send_mail(config, resolve(db, config["passwordRef"]) if config.get("passwordRef") else None, [to],
                  "[BornToShare] E-mail de test", "Les notifications de BornToShare arrivent bien.", test_html)
    except Exception as exc:
        return ui_data({"ok": False, "error": str(exc)[:300]})
    return ui_data({"ok": True})


@router.post("/config/logs/purge", dependencies=[Depends(require_internal_token)])
def purge_old_logs(payload: dict | None = None, db: Session = Depends(get_db)):
    """« Purge old logs » (called by auth-service, which checks the administrator)."""
    from app.services.log_retention import purge_logs

    data = payload if isinstance(payload, dict) else {}
    result = purge_logs(db, trigger="manual", actor_display=str(data.get("actor") or "") or None)
    return ui_data(result)


# ============================================================
# First start: the guided setup shown to an administrator while the application is empty
# ============================================================

def _first_row(db: Session, sql: str) -> dict | None:
    row = db.execute(text(sql)).mappings().first()
    return dict(row) if row else None


@router.get("/setup/status", dependencies=[Depends(admin_or_internal)])
def get_setup_status(db: Session = Depends(get_db)):
    """What is already configured, so that the setup resumes at the right step. No password here."""
    roots = int(db.execute(text("SELECT COUNT(*) FROM storage_roots")).scalar() or 0)
    # An installation that already governs folders has no use for the guided setup
    completed = bool((_read_payload(db).get("setup") or {}).get("completed")) or roots > 0
    zone = _first_row(db, "SELECT id, name, code, description FROM zones ORDER BY id LIMIT 1")
    directory = _first_row(
        db,
        """
        SELECT id, name, directory_flavor, protocol, host, port, domain_name, base_dn, bind_dn,
               bind_password_ref, tls_verify, tls_ca_pem, tls_server_name
        FROM identity_sources WHERE LOWER(type) = 'ad' AND is_active = 1 ORDER BY id LIMIT 1
        """,
    )
    server = _first_row(
        db, "SELECT id, name, host, port, bind_dn, bind_password_ref FROM storage_endpoints ORDER BY id LIMIT 1"
    )
    policy = (
        _first_row(db, f"SELECT static_ou_dn FROM zone_provisioning_policy WHERE zone_id = {int(zone['id'])}") if zone else None
    )
    imported_groups = int(
        db.execute(text("SELECT COUNT(DISTINCT directory_group_id) FROM identity_roles WHERE directory_group_id IS NOT NULL")).scalar() or 0
    )
    return ui_data(
        {
            "completed": completed,
            "zone": zone,
            "directory": directory,
            "group_ou": (policy or {}).get("static_ou_dn"),
            "server": server,
            "imported_groups": imported_groups,
        }
    )


@router.post("/setup/complete", dependencies=[Depends(admin_only)])
async def complete_setup(request: Request, db: Session = Depends(get_db)):
    from app.services.infrastructure_service import register_local_worker

    current = _read_payload(db)
    _write_payload(db, {**current, "setup": {"completed": True}})
    worker = await register_local_worker(db)
    actor = actor_from_request(request)
    log_activity(
        db,
        actor_type="user",
        actor_id=actor.identity_id,
        actor_display=actor.display_name,
        action="advanced_settings.setup_completed",
        outcome="success",
        target_type="advanced_settings",
        target_display="Guided setup",
        context_json={"worker_declared": worker},
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_action(message="setup completed")
