"""Passwords of the directories and file servers: AES-256-GCM in secret_items, referenced as sm://...

The key (B2S_SECRET_MASTER_KEY) stays out of the database: a dump or an SQL access alone gives no password.
The reference is authenticated with the value: a value copied to another row cannot be decrypted.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import text
from sqlalchemy.orm import Session

SM_PREFIX = "sm://"


class SecretError(RuntimeError):
    code = "SECRET_PROVIDER_FAILURE"


class SecretInvalidRef(SecretError):
    code = "SECRET_INVALID_REF"


class SecretNotFound(SecretError):
    code = "SECRET_NOT_FOUND"


class SecretDecryptFailed(SecretError):
    code = "SECRET_DECRYPT_FAILED"


def master_key() -> bytes:
    raw = (os.getenv("B2S_SECRET_MASTER_KEY") or "").strip()
    if not raw:
        raise SecretError("B2S_SECRET_MASTER_KEY is required")
    try:
        decoded = base64.b64decode(raw, validate=True)
        if len(decoded) == 32:
            return decoded
    except ValueError:
        pass
    if len(raw) == 64:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass
    if len(raw) < 16:
        raise SecretError("B2S_SECRET_MASTER_KEY too weak (min 16 chars)")
    return hashlib.sha256(raw.encode("utf-8")).digest()


def build_ref(name_or_ref: str) -> str:
    raw = str(name_or_ref or "").strip().replace("\\", "/")
    if raw.startswith(SM_PREFIX):
        raw = raw[len(SM_PREFIX):]
    if raw.startswith("/") or ".." in raw.split("/"):
        raise SecretInvalidRef("Secret reference is invalid")
    parts = [part for part in raw.split("/") if part and part != "."]
    if not parts:
        raise SecretInvalidRef("Empty secret reference")
    return SM_PREFIX + "/".join(parts)


def encrypt(ref: str, value: str) -> tuple[str, str]:
    iv = os.urandom(12)
    ciphertext = AESGCM(master_key()).encrypt(iv, value.encode("utf-8"), ref.encode("utf-8"))
    return base64.b64encode(iv).decode("ascii"), base64.b64encode(ciphertext).decode("ascii")


def store(db: Session, name: str, value: str) -> str:
    ref = build_ref(name)
    iv, ciphertext = encrypt(ref, value)
    db.execute(
        text(
            """
            INSERT INTO secret_items (ref, name, iv, ciphertext, key_id) VALUES (:ref, :name, :iv, :ciphertext, 'master')
            ON DUPLICATE KEY UPDATE iv = VALUES(iv), ciphertext = VALUES(ciphertext)
            """
        ),
        {"ref": ref, "name": name, "iv": iv, "ciphertext": ciphertext},
    )
    db.commit()
    return ref


def resolve(db: Session, ref: str) -> str:
    checked = build_ref(ref)
    row = db.execute(
        text("SELECT iv, ciphertext FROM secret_items WHERE ref = :ref"), {"ref": checked}
    ).mappings().first()
    if row is None:
        raise SecretNotFound("Secret not found")
    try:
        return AESGCM(master_key()).decrypt(
            base64.b64decode(row["iv"]), base64.b64decode(row["ciphertext"]), checked.encode("utf-8")
        ).decode("utf-8")
    except Exception as exc:
        raise SecretDecryptFailed("Secret exists but cannot be decrypted") from exc


def exists(db: Session, ref: str) -> bool:
    return db.execute(text("SELECT 1 FROM secret_items WHERE ref = :ref"), {"ref": build_ref(ref)}).first() is not None
