"""Response envelopes shared by every route: {"data": ..., "meta": {...}}."""
from __future__ import annotations

from typing import Any


def ui_data(data: Any, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "data": data,
        "meta": dict(meta or {}),
    }


def ui_list(items: list[Any], *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved_meta = dict(meta or {})
    resolved_meta.setdefault("count", len(items))
    return {
        "data": items,
        "meta": resolved_meta,
    }


def ui_action(
    *,
    ok: bool = True,
    message: str | None = None,
    action_id: int | str | None = None,
    details: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": bool(ok),
        "id": action_id,
        "message": message,
        "details": details,
    }
    return {
        "data": payload,
        "meta": dict(meta or {}),
    }
