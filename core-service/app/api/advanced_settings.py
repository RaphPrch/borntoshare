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
from app.services.authorization import actor_from_request, admin_or_internal

router = APIRouter(prefix="/admin", tags=["advanced-settings"])


# "logging" is read by auth-service, "governance" by core-service; other sections were stored but never applied.
DEFAULT_ADVANCED_SETTINGS: dict = {
    "logging": {
        "level": "INFO",
        "retentionEnabled": True,
        "retentionDays": 180,
    },
    "governance": {
        "minGuardians": 2,
    },
}

MIN_GUARDIANS_RANGE = (1, 10)


DEPRECATED_ADVANCED_SETTINGS_KEYS = {"platform", "discovery", "integrations", "security", "sessions", "maintenance"}


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


def min_guardians(db: Session) -> int:
    """Guardians a storage root must have (Advanced settings > Governance)."""
    value = (_read_payload(db).get("governance") or {}).get("minGuardians")
    low, high = MIN_GUARDIANS_RANGE
    return value if isinstance(value, int) and low <= value <= high else DEFAULT_ADVANCED_SETTINGS["governance"]["minGuardians"]


def _changed_settings(before: dict, after: dict, prefix: str = "") -> dict:
    changes: dict = {}
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if isinstance(old, dict) and isinstance(new, dict):
            changes.update(_changed_settings(old, new, f"{prefix}{key}."))
        elif old != new:
            changes[f"{prefix}{key}"] = {"from": old, "to": new}
    return changes


@router.get("/config/advanced", dependencies=[Depends(admin_or_internal)])
def get_advanced_config(db: Session = Depends(get_db)):
    return ui_data(_read_payload(db))


@router.post("/config/advanced", dependencies=[Depends(admin_or_internal)])
def save_advanced_config(payload: dict, request: Request, db: Session = Depends(get_db)):
    from app.services.log_retention import apply_log_level

    current = _read_payload(db)
    merged = _sanitize_advanced_settings(_deep_merge(current, payload if isinstance(payload, dict) else {}))
    wanted = (merged.get("governance") or {}).get("minGuardians")
    low, high = MIN_GUARDIANS_RANGE
    if not isinstance(wanted, int) or isinstance(wanted, bool) or not low <= wanted <= high:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "MIN_GUARDIANS_INVALID", "message": f"Le nombre de garants doit être compris entre {low} et {high}."},
        )
    _write_payload(db, merged)
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


@router.post("/config/logs/purge", dependencies=[Depends(require_internal_token)])
def purge_old_logs(payload: dict | None = None, db: Session = Depends(get_db)):
    """« Purge old logs » (called by auth-service, which checks the administrator)."""
    from app.services.log_retention import purge_logs

    data = payload if isinstance(payload, dict) else {}
    result = purge_logs(db, trigger="manual", actor_display=str(data.get("actor") or "") or None)
    return ui_data(result)

