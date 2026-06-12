from __future__ import annotations

from typing import Any, Mapping


def ok_data(data: Any, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "meta": dict(meta or {}),
        "error": None,
    }


def error_payload(
    *,
    code: str,
    message: str,
    request_id: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    if request_id:
        meta["request_id"] = str(request_id)

    return {
        "ok": False,
        "data": None,
        "meta": meta,
        "error": {
            "code": str(code),
            "message": str(message),
            "details": dict(extra or {}),
        },
    }
