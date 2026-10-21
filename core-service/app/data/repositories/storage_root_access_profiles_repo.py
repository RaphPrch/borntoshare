"""Access groups of storage roots (storage_root_access_profiles).

One AD group per storage root and access level (READ/WRITE), created on the first
approved request for that level and reused afterwards.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

ACCESS_LEVELS = ("READ", "WRITE")

_COLUMNS = """
    id, storage_root_id, access_level_code, group_name, group_external_id,
    status, error_message, created_at, updated_at
"""


class StorageRootAccessProfilesRepo:
    def __init__(self, db: Session):
        self.db = db

    def get(self, profile_id: int) -> dict[str, Any] | None:
        row = self.db.execute(
            text(f"SELECT {_COLUMNS} FROM storage_root_access_profiles WHERE id = :id"),
            {"id": int(profile_id)},
        ).mappings().first()
        return dict(row) if row else None

    def list_by_root(self, *, storage_root_id: int, access_level_code: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"storage_root_id": int(storage_root_id)}
        level_filter = ""
        if access_level_code:
            level_filter = "AND access_level_code = :access_level_code"
            params["access_level_code"] = str(access_level_code).strip().upper()
        rows = self.db.execute(
            text(
                f"""
                SELECT {_COLUMNS}
                FROM storage_root_access_profiles
                WHERE storage_root_id = :storage_root_id {level_filter}
                ORDER BY access_level_code ASC
                """
            ),
            params,
        ).mappings().all()
        return [dict(r) for r in rows]

    def get_for_level(self, *, storage_root_id: int, access_level_code: str) -> dict[str, Any] | None:
        rows = self.list_by_root(storage_root_id=storage_root_id, access_level_code=access_level_code)
        return rows[0] if rows else None

    def ensure(self, *, storage_root_id: int, access_level_code: str, group_name: str) -> tuple[dict[str, Any], bool]:
        """Return the group of this level, creating it (PENDING) if it does not exist yet.

        An existing group keeps its name: `group_name` only applies on creation.
        Returns (row, created). The caller commits.
        """
        level = str(access_level_code).strip().upper()
        if level not in ACCESS_LEVELS:
            raise ValueError(f"access level must be one of {ACCESS_LEVELS}")
        existing = self.get_for_level(storage_root_id=storage_root_id, access_level_code=level)
        if existing:
            return existing, False
        self.db.execute(
            text(
                """
                INSERT IGNORE INTO storage_root_access_profiles (storage_root_id, access_level_code, group_name, status)
                VALUES (:storage_root_id, :access_level_code, :group_name, 'PENDING')
                """
            ),
            {"storage_root_id": int(storage_root_id), "access_level_code": level, "group_name": str(group_name).strip()},
        )
        row = self.get_for_level(storage_root_id=storage_root_id, access_level_code=level)
        if row is None:
            raise RuntimeError("storage root access group could not be created")
        return row, True

    def mark_adoption(self, profile_id: int, *, group_dn: str) -> None:
        """Point the level at an existing AD group; the next grant job adopts it. The caller commits."""
        self.db.execute(
            text(
                """
                UPDATE storage_root_access_profiles
                SET status = 'ADOPTING', group_external_id = :group_dn, error_message = NULL
                WHERE id = :id
                """
            ),
            {"id": int(profile_id), "group_dn": str(group_dn).strip()},
        )

    def record_outcome(
        self,
        profile_id: int,
        *,
        succeeded: bool,
        group_external_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Store the result of the AD group creation job. The caller commits."""
        self.db.execute(
            text(
                """
                UPDATE storage_root_access_profiles
                SET status = :status,
                    group_external_id = COALESCE(:group_external_id, group_external_id),
                    error_message = :error_message
                WHERE id = :id
                """
            ),
            {
                "id": int(profile_id),
                "status": "SUCCEEDED" if succeeded else "FAILED",
                "group_external_id": (str(group_external_id).strip() or None) if group_external_id else None,
                "error_message": None if succeeded else (str(error_message or "").strip()[:2000] or None),
            },
        )
