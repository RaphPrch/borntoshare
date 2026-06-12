from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _as_text_clause(sql: str):
    return text(sql)


def fetch_all(db: Session, sql: str, params: dict | None = None):
    """Execute SQL and return a list of RowMapping (dict-like) rows."""

    return db.execute(_as_text_clause(sql), params or {}).mappings().all()


def fetch_one(db: Session, sql: str, params: dict | None = None):
    """Execute SQL and return the first RowMapping (dict-like) row or None."""

    return db.execute(_as_text_clause(sql), params or {}).mappings().first()


def to_dicts(rows: Any) -> list[dict]:
    """Normalize SQLAlchemy results to JSON-serializable list[dict].

    Handles:
    - list[RowMapping]
    - Result.mappings().all() output
    - None
    """

    if not rows:
        return []
    return [dict(r) for r in rows]


def to_dict(row: Any) -> dict | None:
    if not row:
        return None
    return dict(row)

