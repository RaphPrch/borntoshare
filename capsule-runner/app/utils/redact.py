from __future__ import annotations

from typing import Any

SENSITIVE_KEYS = {"password", "secret", "token", "keytab", "bind_password", "authorization"}


def redact_dict(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in SENSITIVE_KEYS or lk.endswith("_password") or lk.endswith("_token"):
                out[k] = "***"
            elif lk == "value" and isinstance(v, str):
                out[k] = "***"
            else:
                out[k] = redact_dict(v)
        return out
    if isinstance(obj, list):
        return [redact_dict(v) for v in obj]
    return obj

