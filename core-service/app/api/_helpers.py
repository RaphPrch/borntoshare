from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.sql import fetch_all as _fetch_all
from app.core.sql import fetch_one as _fetch_one
from app.core.sql import to_dicts


def fetch_all(db: Session, sql: str, params: dict | None = None):
    return _fetch_all(db, sql, params)


def fetch_one(db: Session, sql: str, params: dict | None = None):
    return _fetch_one(db, sql, params)


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
