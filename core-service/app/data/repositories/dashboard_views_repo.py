from __future__ import annotations

from sqlalchemy.orm import Session

from app.data.repositories.sql_view_repo import SQLViewRepo


class DashboardViewsRepo(SQLViewRepo):
    """Read-model repository for dashboard views."""

    def __init__(self, db: Session):
        super().__init__(db)

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
