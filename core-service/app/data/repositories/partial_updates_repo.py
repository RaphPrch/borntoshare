"""Partial updates (only the fields sent): the column names come from a fixed list per table, never from the request."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# table -> (key column, columns that may be set)
_TABLES: dict[str, tuple[str, frozenset[str]]] = {
    "zones": ("id", frozenset({"name", "code", "description"})),
    "infra_workers": ("id", frozenset({"name", "host", "port", "use_tls", "verify_tls", "is_enabled"})),
    "infra_schedules": ("task", frozenset({"is_enabled", "interval_minutes", "options_json"})),
}


def update_columns(db: Session, table: str, key: Any, values: dict[str, Any], *, reschedule_minutes: bool = False) -> int:
    """UPDATE <table> SET <the given columns> WHERE <key column> = key. reschedule_minutes (infra_schedules): the next
    run moves to now + the new interval. Raises ValueError for a table or a column not in the list."""
    key_column, allowed = _TABLES[table]
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"columns not allowed on {table}: {sorted(unknown)}")
    if not values:
        return 0
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    if reschedule_minutes:
        assignments += ", next_run_at = UTC_TIMESTAMP() + INTERVAL :interval_minutes MINUTE"
    result = db.execute(text(f"UPDATE {table} SET {assignments} WHERE {key_column} = :_key"), {**values, "_key": key})
    return int(getattr(result, "rowcount", 0) or 0)
