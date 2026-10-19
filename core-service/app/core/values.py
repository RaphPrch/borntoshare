"""Small value helpers shared across services and routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def positive_int(value: Any) -> int | None:
    """int(value) when it is a positive integer, else None."""
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def utcnow_naive() -> datetime:
    """Current UTC time without tzinfo (the database stores naive UTC datetimes)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def unwrap_data(payload: Any) -> Any:
    """`payload["data"]` for a {"data": ...} envelope, else the payload itself."""
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def unwrap_data_dict(payload: Any) -> dict[str, Any] | None:
    data = unwrap_data(payload)
    return data if isinstance(data, dict) else None


def unwrap_list(payload: Any) -> list[dict[str, Any]]:
    """Rows of a list payload: a bare list, or an envelope's "items"/"data" list."""
    if isinstance(payload, dict):
        payload = payload.get("items") if isinstance(payload.get("items"), list) else payload.get("data")
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]
