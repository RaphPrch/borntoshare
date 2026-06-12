from __future__ import annotations

from typing import Any, Mapping


def ok_data(data: Any, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "meta": dict(meta or {}),
        "error": None,
    }


def error_payload(*, code: str, message: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "data": None,
        "meta": {},
        "error": {
            "code": str(code),
            "message": str(message),
            "details": dict(details or {}),
        },
    }

