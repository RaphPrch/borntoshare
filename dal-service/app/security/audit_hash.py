from __future__ import annotations

import hashlib
import json
from typing import Any

SENSITIVE_KEYS = {"password", "secret", "token", "keytab", "bind_password", "authorization"}


def scrub_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            lk = str(k).lower()
            if lk in SENSITIVE_KEYS:
                out[k] = "***"
            else:
                out[k] = scrub_secrets(v)
        return out
    if isinstance(value, list):
        return [scrub_secrets(v) for v in value]
    return value


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_event_hash(prev_hash: str | None, payload: dict[str, Any]) -> str:
    seed = f"{prev_hash or ''}{canonical_json(payload)}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()

