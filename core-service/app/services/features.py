"""Optional modules of BornToShare, opened by a signed license key and switched on by an administrator.

A license key (B2S-XXXXX-…) carries: its id, the customer, the features it opens, the day it was issued, the last day
it is valid, and limits. It is checked offline against the public keys of app.core.license_keys: nobody can make one
without the private key of the issuer. A feature is usable when a valid license opens it AND it is switched on
(feature_flags): it can stay licensed and off.
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# The modules the application knows. A key may open features of a later version: they are listed, not usable.
FEATURES: dict[str, dict[str, str]] = {
    "fives": {
        "label": "5S et hygiène des données",
        "description": "Score 5S des partages, doublons, âge des données, fichiers parasites, croissance, "
                       "scanner dédié sur les serveurs (sans agent) et rapport 5S.",
        "icon": "bi-stars",
    },
}


class LicenseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class License:
    license_id: str
    customer: str
    features: tuple[str, ...]
    issued_on: date | None
    expires_on: date | None
    limits: dict[str, Any]
    key_hash: str
    key_hint: str

    def valid_on(self, day: date) -> bool:
        return self.expires_on is None or day <= self.expires_on


def _today() -> date:
    return datetime.now(timezone.utc).date()


def normalize(key: str) -> str:
    """« b2s-abcde fghij » → « B2S-ABCDE-FGHIJ »: spaces, line breaks and case do not matter."""
    compact = "".join(ch for ch in str(key or "").upper() if ch.isalnum())
    if compact.startswith("B2S"):
        compact = compact[3:]
    return compact


def decode(key: str) -> License:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization

    from app.core.license_keys import PUBLIC_KEYS

    compact = normalize(key)
    if len(compact) < 40:
        raise LicenseError("LICENSE_MALFORMED", "This is not a BornToShare license key")
    try:
        blob = base64.b32decode(compact + "=" * (-len(compact) % 8))
        version, length = struct.unpack(">BH", blob[:3])
        body, signature = blob[3:3 + length], blob[3 + length:]
    except (ValueError, struct.error) as exc:
        raise LicenseError("LICENSE_MALFORMED", "This is not a BornToShare license key") from exc
    if version != 1 or len(signature) != 64 or len(body) != length:
        raise LicenseError("LICENSE_MALFORMED", "This is not a BornToShare license key")
    signed = blob[:3 + length]
    for pem in PUBLIC_KEYS:
        public = serialization.load_pem_public_key(pem.encode())
        try:
            public.verify(signature, signed)
            break
        except InvalidSignature:
            continue
    else:
        raise LicenseError("LICENSE_SIGNATURE_INVALID", "This key was not issued for BornToShare (signature refused)")
    payload = json.loads(body)
    parse = lambda value: date.fromisoformat(value) if value else None  # noqa: E731
    return License(
        license_id=str(payload.get("lic") or ""), customer=str(payload.get("cust") or ""),
        features=tuple(sorted(str(item) for item in payload.get("feat") or [])),
        issued_on=parse(payload.get("iat")), expires_on=parse(payload.get("exp")),
        limits=dict(payload.get("lim") or {}),
        key_hash=hashlib.sha256(compact.encode()).hexdigest(), key_hint=f"…{compact[-8:]}",
    )


def _licenses(db: Session) -> list[dict[str, Any]]:
    try:
        rows = db.execute(text("SELECT * FROM licenses WHERE removed_at IS NULL ORDER BY activated_at")).mappings().all()
    except Exception:
        db.rollback()
        return []
    out = []
    for row in rows:
        out.append({
            "id": int(row["id"]), "license_id": row["license_id"], "customer": row["customer"], "key_hint": row["key_hint"],
            "features": json.loads(row["features_json"] or "[]"), "limits": json.loads(row["limits_json"] or "{}"),
            "issued_on": row["issued_on"].isoformat() if row["issued_on"] else None,
            "expires_on": row["expires_on"].isoformat() if row["expires_on"] else None,
            "expired": bool(row["expires_on"] and row["expires_on"] < _today()),
            "activated_at": row["activated_at"].isoformat() + "Z" if row["activated_at"] else None, "activated_by": row["activated_by"],
        })
    return out


def _flags(db: Session) -> dict[str, dict[str, Any]]:
    try:
        rows = db.execute(text("SELECT feature, enabled, settings_json, updated_by, updated_at FROM feature_flags")).mappings().all()
    except Exception:
        db.rollback()
        return {}
    return {row["feature"]: {"enabled": bool(row["enabled"]), "settings": json.loads(row["settings_json"] or "{}"),
                             "updated_by": row["updated_by"], "updated_at": row["updated_at"].isoformat() + "Z" if row["updated_at"] else None}
            for row in rows}


def installed(feature: str) -> bool:
    """Does the module run on this installation? (its container answers, its databases are there)"""
    from app.services import modules

    return modules.fives_installed() if feature == "fives" else True


def state(db: Session) -> dict[str, Any]:
    """Every known feature: is it licensed (until when, by which license), switched on, installed; usable (enabled)
    only when all three: the menu and the pages of a module never show while it cannot answer."""
    licenses = _licenses(db)
    flags = _flags(db)
    features = []
    for key, meta in FEATURES.items():
        valid = [lic for lic in licenses if key in lic["features"] and not lic["expired"]]
        expires = max((lic["expires_on"] or "9999-12-31" for lic in valid), default=None)
        flag = flags.get(key) or {}
        licensed = bool(valid)
        switched_on = bool(flag.get("enabled"))
        ready = installed(key) if licensed and switched_on else False
        features.append({"key": key, **meta, "licensed": licensed, "expires_on": None if expires == "9999-12-31" else expires,
                         "enabled": licensed and switched_on and ready, "switched_on": switched_on, "installed": ready,
                         "settings": flag.get("settings") or {}, "updated_by": flag.get("updated_by"), "updated_at": flag.get("updated_at")})
    return {"features": features, "licenses": licenses}


def enabled(db: Session, feature: str) -> bool:
    return any(item["key"] == feature and item["enabled"] for item in state(db)["features"])


def require(db: Session, feature: str) -> None:
    from fastapi import HTTPException, status

    if not enabled(db, feature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "error_code": "FEATURE_DISABLED", "message": "This feature is not active: an administrator turns it on in Advanced settings › Features",
            "feature": feature})


def activate(db: Session, key: str, by: str | None) -> License:
    lic = decode(key)
    if not lic.valid_on(_today()):
        raise LicenseError("LICENSE_EXPIRED", f"This key expired on {lic.expires_on.isoformat() if lic.expires_on else ''}")
    known = [feature for feature in lic.features if feature in FEATURES]
    if not known:
        raise LicenseError("LICENSE_NO_FEATURE", "This key opens no feature of this version of BornToShare")
    db.execute(
        text(
            """
            INSERT INTO licenses (license_id, key_hash, key_hint, customer, features_json, limits_json, issued_on, expires_on, activated_by)
            VALUES (:lic, :hash, :hint, :cust, :feat, :lim, :iat, :exp, :by)
            ON DUPLICATE KEY UPDATE removed_at = NULL, removed_by = NULL, activated_at = CURRENT_TIMESTAMP, activated_by = VALUES(activated_by)
            """
        ),
        {"lic": lic.license_id, "hash": lic.key_hash, "hint": lic.key_hint, "cust": lic.customer[:190], "feat": json.dumps(list(lic.features)),
         "lim": json.dumps(lic.limits), "iat": lic.issued_on, "exp": lic.expires_on, "by": by},
    )
    db.commit()
    return lic


def remove_license(db: Session, license_row_id: int, by: str | None) -> bool:
    result = db.execute(text("UPDATE licenses SET removed_at = CURRENT_TIMESTAMP, removed_by = :by WHERE id = :id AND removed_at IS NULL"),
                        {"id": int(license_row_id), "by": by})
    db.commit()
    return bool(result.rowcount)


def switch(db: Session, feature: str, on: bool, by: str | None, settings: dict[str, Any] | None = None) -> None:
    db.execute(
        text(
            """
            INSERT INTO feature_flags (feature, enabled, settings_json, updated_by) VALUES (:f, :on, :settings, :by)
            ON DUPLICATE KEY UPDATE enabled = VALUES(enabled), updated_by = VALUES(updated_by),
              settings_json = COALESCE(VALUES(settings_json), settings_json)
            """
        ),
        {"f": feature, "on": 1 if on else 0, "settings": json.dumps(settings) if settings is not None else None, "by": by},
    )
    db.commit()
