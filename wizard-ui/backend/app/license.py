"""License keys (B2S-XXXXX-…) checked offline, as core-service does (app/services/features.py): the wizard records the
key in the database of BornToShare and switches its modules on; the application then shows it in Réglages avancés ›
Fonctionnalités."""
from __future__ import annotations

import base64
import hashlib
import json
import struct
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

# The modules this version knows (same keys as core-service FEATURES)
FEATURES = {"fives": "5S et hygiène des données"}


class LicenseError(ValueError):
    pass


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

    def expired(self) -> bool:
        return self.expires_on is not None and datetime.now(timezone.utc).date() > self.expires_on

    def public(self) -> dict[str, Any]:
        return {
            "license_id": self.license_id, "customer": self.customer, "key_hint": self.key_hint,
            "issued_on": self.issued_on.isoformat() if self.issued_on else None,
            "expires_on": self.expires_on.isoformat() if self.expires_on else None, "expired": self.expired(),
            "features": [{"key": key, "label": FEATURES.get(key, key), "known": key in FEATURES} for key in self.features],
        }


def _normalize(key: str) -> str:
    compact = "".join(ch for ch in str(key or "").upper() if ch.isalnum())
    return compact[3:] if compact.startswith("B2S") else compact


def decode(key: str) -> License:
    """The license carried by the key; LicenseError when it is not a key signed for BornToShare, expired or opens nothing."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization

    from .license_keys import PUBLIC_KEYS

    compact = _normalize(key)
    malformed = LicenseError("Ce n'est pas une clé de licence BornToShare.")
    if len(compact) < 40:
        raise malformed
    try:
        blob = base64.b32decode(compact + "=" * (-len(compact) % 8))
        version, length = struct.unpack(">BH", blob[:3])
    except (ValueError, struct.error) as exc:
        raise malformed from exc
    body, signature = blob[3:3 + length], blob[3 + length:]
    if version != 1 or len(signature) != 64 or len(body) != length:
        raise malformed
    for pem in PUBLIC_KEYS:
        try:
            serialization.load_pem_public_key(pem.encode()).verify(signature, blob[:3 + length])
            break
        except InvalidSignature:
            continue
    else:
        raise LicenseError("Cette clé n'a pas été émise pour BornToShare (signature refusée).")
    payload = json.loads(body)
    parse = lambda value: date.fromisoformat(value) if value else None  # noqa: E731
    lic = License(
        license_id=str(payload.get("lic") or ""), customer=str(payload.get("cust") or ""),
        features=tuple(sorted(str(item) for item in payload.get("feat") or [])),
        issued_on=parse(payload.get("iat")), expires_on=parse(payload.get("exp")), limits=dict(payload.get("lim") or {}),
        key_hash=hashlib.sha256(compact.encode()).hexdigest(), key_hint=f"…{compact[-8:]}",
    )
    if lic.expired():
        raise LicenseError(f"Cette clé a expiré le {lic.expires_on.strftime('%d/%m/%Y')}.")
    if not any(feature in FEATURES for feature in lic.features):
        raise LicenseError("Cette clé n'ouvre aucun module de cette version de BornToShare.")
    return lic


def record(cur, lic: License, *, by: str, switch_on: list[str]) -> None:
    """The license in the database of BornToShare (as Réglages avancés › Fonctionnalités does) and its modules switched on."""
    cur.execute(
        """
        INSERT INTO licenses (license_id, key_hash, key_hint, customer, features_json, limits_json, issued_on, expires_on, activated_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE removed_at = NULL, removed_by = NULL, activated_at = CURRENT_TIMESTAMP, activated_by = VALUES(activated_by)
        """,
        (lic.license_id, lic.key_hash, lic.key_hint, lic.customer[:190], json.dumps(list(lic.features)), json.dumps(lic.limits),
         lic.issued_on, lic.expires_on, by),
    )
    for feature in switch_on:
        cur.execute(
            "INSERT INTO feature_flags (feature, enabled, updated_by) VALUES (%s, 1, %s) "
            "ON DUPLICATE KEY UPDATE enabled = 1, updated_by = VALUES(updated_by)",
            (feature, by),
        )
