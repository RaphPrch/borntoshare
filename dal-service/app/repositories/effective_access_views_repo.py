from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.sql_view_repo import SQLViewRepo


class EffectiveAccessViewsRepo(SQLViewRepo):
    """Read repository for effective access SQL views."""

    def __init__(self, db: Session):
        super().__init__(db)

    def list_storage_root_effective_access(self, *, limit: int = 500) -> list[dict]:
        lim = max(1, min(int(limit or 500), 5000))
        return self._all_dicts(
            """
            SELECT
                storage_root_id,
                storage_root_name,
                identity_source_id,
                directory_snapshot_id,
                actor_id,
                actor_external_id,
                actor_display_name,
                access_level,
                granted_at,
                expires_at,
                source
            FROM v_storage_root_effective_access
            ORDER BY COALESCE(granted_at, '1970-01-01') DESC, storage_root_id ASC
            LIMIT :limit
            """,
            {"limit": lim},
        )

    def list_dashboard_user_effective_access(
        self,
        *,
        requester_identity_id: int | None = None,
        limit: int = 500,
    ) -> list[dict]:
        lim = max(1, min(int(limit or 500), 5000))
        return self._all_dicts(
            """
            SELECT
                requester_identity_id,
                storage_root_id,
                storage_root_name,
                identity_source_id,
                directory_snapshot_id,
                access_level,
                access_profile_code,
                granted_at,
                expires_at,
                actor_id,
                actor_display_name,
                source
            FROM v_dashboard_user_effective_access
            WHERE (:requester_identity_id IS NULL OR requester_identity_id = :requester_identity_id)
            ORDER BY COALESCE(granted_at, '1970-01-01') DESC, storage_root_id ASC
            LIMIT :limit
            """,
            {
                "requester_identity_id": int(requester_identity_id) if requester_identity_id is not None else None,
                "limit": lim,
            },
        )

