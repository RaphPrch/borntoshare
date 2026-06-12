from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.sql_view_repo import SQLViewRepo


class DashboardViewsRepo(SQLViewRepo):
    """Read-model repository for dashboard views."""

    def __init__(self, db: Session):
        super().__init__(db)

    def get_summary(self, *, requester_identity_id: int | None = None) -> dict:
        row = self._one_dict(
            """
            SELECT *
            FROM v_dashboard_user_summary
            WHERE (:requester_identity_id IS NULL OR requester_identity_id = :requester_identity_id)
            ORDER BY total_requests DESC
            LIMIT 1
            """,
            {
                "requester_identity_id": int(requester_identity_id) if requester_identity_id is not None else None,
            },
        )
        return row or {}

    def list_latest_requests(self, *, requester_identity_id: int | None = None, limit: int = 10) -> list[dict]:
        lim = max(1, min(int(limit or 10), 100))
        return self._all_dicts(
            """
            SELECT *
            FROM v_dashboard_user_latest_requests
            WHERE (:requester_identity_id IS NULL OR requester_identity_id = :requester_identity_id)
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {
                "requester_identity_id": int(requester_identity_id) if requester_identity_id is not None else None,
                "limit": lim,
            },
        )

    def list_effective_access(self, *, requester_identity_id: int | None = None, limit: int = 20) -> list[dict]:
        lim = max(1, min(int(limit or 20), 200))
        return self._all_dicts(
            """
            SELECT *
            FROM v_dashboard_user_effective_access
            WHERE (:requester_identity_id IS NULL OR requester_identity_id = :requester_identity_id)
            ORDER BY COALESCE(granted_at, '1970-01-01') DESC
            LIMIT :limit
            """,
            {
                "requester_identity_id": int(requester_identity_id) if requester_identity_id is not None else None,
                "limit": lim,
            },
        )

    def get_platform_overview(self) -> dict:
        payload = self._one_dict("SELECT * FROM v_dashboard_overview") or {}
        admins_row = self._one_dict(
            """
            SELECT COUNT(*) AS admins_count
            FROM (
              SELECT DISTINCT identity_id
              FROM v_identity_effective_roles
              WHERE role_code = 'platform_admin'
            ) admins
            """
        )
        payload["admins_count"] = int((admins_row or {}).get("admins_count") or 0)
        return payload

    def list_access_requests_expiring_soon(
        self,
        *,
        requester_identity_id: int | None = None,
        limit: int = 200,
    ) -> list[dict]:
        lim = max(1, min(int(limit or 200), 1000))
        return self._all_dicts(
            """
            SELECT *
            FROM v_access_requests_expiring_soon
            WHERE (:requester_identity_id IS NULL OR requester_id = :requester_identity_id)
            ORDER BY hours_remaining ASC
            LIMIT :limit
            """,
            {
                "requester_identity_id": int(requester_identity_id) if requester_identity_id is not None else None,
                "limit": lim,
            },
        )
