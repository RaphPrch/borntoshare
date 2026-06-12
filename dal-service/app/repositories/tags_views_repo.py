from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.sql_view_repo import SQLViewRepo


class TagsViewsRepo(SQLViewRepo):
    """
    Read-model repository for Tags (v4 minimal)

    Backed by base table:
      - tags
    """

    def __init__(self, db: Session):
        super().__init__(db)

    # ============================================================
    # LIST
    # ============================================================

    def list(self) -> list[dict]:
        """
        List all tags.

        Used by:
        - Tags management page
        - Dataspace / StorageRoot tagging
        """
        # Usage = number of attachments across supported association tables.
        # Today only storage_root_tags is persisted at DB-level.
        return self._all_dicts(
            """
            SELECT
                t.id,
                t.name,
                t.color,
                COALESCE(u.tag_usage, 0) AS `usage`
            FROM tags t
            LEFT JOIN (
                SELECT tag_id, COUNT(*) AS tag_usage
                FROM storage_root_tags
                GROUP BY tag_id
            ) u ON u.tag_id = t.id
            ORDER BY t.name
            """
        )

    def get(self, tag_id: int) -> dict | None:
        """
        Single tag overview.
        """
        return self._one_dict(
            """
            SELECT
                t.id,
                t.name,
                t.color,
                COALESCE(u.tag_usage, 0) AS `usage`
            FROM tags t
            LEFT JOIN (
                SELECT tag_id, COUNT(*) AS tag_usage
                FROM storage_root_tags
                GROUP BY tag_id
            ) u ON u.tag_id = t.id
            WHERE t.id = :id
            """,
            {"id": int(tag_id)},
        )
