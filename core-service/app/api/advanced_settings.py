from __future__ import annotations

import json
from copy import deepcopy
from json import JSONDecodeError

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.api._helpers import ui_action, ui_data

router = APIRouter(prefix="/admin", tags=["advanced-settings"])


# Only "logging" is read (by auth-service); other sections were stored but never applied.
DEFAULT_ADVANCED_SETTINGS: dict = {
    "logging": {
        "level": "INFO",
        "retentionEnabled": True,
        "retentionDays": 180,
    },
}


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


@router.get("/config/advanced")
def get_advanced_config(db: Session = Depends(get_db)):
    return ui_data(_read_payload(db))


@router.post("/config/advanced")
def save_advanced_config(payload: dict, db: Session = Depends(get_db)):
    current = _read_payload(db)
    merged = _deep_merge(current, payload if isinstance(payload, dict) else {})
    _write_payload(db, _sanitize_advanced_settings(merged))
    return ui_action(message="advanced settings saved")

