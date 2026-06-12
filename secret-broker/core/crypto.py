from __future__ import annotations

import base64
import hashlib
import os


def get_master_key_id() -> str:
    return (os.getenv("B2S_SECRET_MASTER_KEY_ID") or "dev-master").strip()


def get_master_key() -> bytes:
    raw = (os.getenv("B2S_SECRET_MASTER_KEY") or "").strip()
    if not raw:
        raise RuntimeError("B2S_SECRET_MASTER_KEY is required")

    try:
        decoded = base64.b64decode(raw, validate=True)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass

    if len(raw) == 64:
        try:
            return bytes.fromhex(raw)
        except Exception:
            pass

    if len(raw) < 16:
        raise RuntimeError("B2S_SECRET_MASTER_KEY too weak (min 16 chars)")

    return hashlib.sha256(raw.encode("utf-8")).digest()

