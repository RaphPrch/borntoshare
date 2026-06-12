from __future__ import annotations

from typing import Any, Mapping


def ok_data(data: Any, *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "meta": dict(meta or {}),
        "error": None,
    }


def ok_list(items: list[Any], *, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    resolved_meta: dict[str, Any] = {"count": len(items)}
    if meta:
        resolved_meta.update(dict(meta))
    return {
        "ok": True,
        "data": items,
        "meta": resolved_meta,
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


def data_envelope(data: Any) -> dict[str, Any]:
    return ok_data(data)


def list_envelope(items: list[Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return ok_list(items, meta=meta)
