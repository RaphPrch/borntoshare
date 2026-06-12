from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.sql import fetch_all, fetch_one, to_dict, to_dicts


class SQLViewRepo:
    """Base class for read-model repositories backed by SQL views/tables.

    Goal: standardize naming and reduce boilerplate.
    """

    def __init__(self, db: Session):
        self.db = db

    # -----------------
    # Low-level helpers
    # -----------------

    def _all(self, sql: str, params: dict | None = None):
        return fetch_all(self.db, sql, params)

    def _one(self, sql: str, params: dict | None = None):
        return fetch_one(self.db, sql, params)

    def _all_dicts(self, sql: str, params: dict | None = None) -> list[dict]:
        return to_dicts(self._all(sql, params))

    def _one_dict(self, sql: str, params: dict | None = None) -> dict | None:
        return to_dict(self._one(sql, params))

