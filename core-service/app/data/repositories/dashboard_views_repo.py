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

        # Items that need an operator's attention
        attention = self._one_dict(
            """
            SELECT
              (SELECT COUNT(*) FROM governance_alerts WHERE LOWER(status) = 'open') AS open_alerts_count,
              (SELECT COUNT(*) FROM governance_alerts
                WHERE LOWER(status) = 'open' AND LOWER(severity) IN ('critical', 'high')) AS critical_alerts_count,
              (SELECT COUNT(*) FROM provisioning_jobs
                WHERE status = 'FAILED' AND COALESCE(finished_at, updated_at) >= NOW() - INTERVAL 1 DAY) AS failed_jobs_24h_count,
              (SELECT COUNT(*) FROM access_requests
                WHERE status = 'pending' AND created_at < NOW() - INTERVAL 3 DAY) AS stale_pending_requests_count
            """
        ) or {}
        for key, value in attention.items():
            payload[key] = int(value or 0)

        # Access requests submitted per day over the last 30 days (days without requests are omitted)
        rows = self._all_dicts(
            """
            SELECT
              DATE(created_at) AS day,
              COUNT(*) AS submitted,
              SUM(CASE WHEN status IN ('executed', 'approved', 'enforced') THEN 1 ELSE 0 END) AS applied
            FROM access_requests
            WHERE created_at >= CURDATE() - INTERVAL 29 DAY
            GROUP BY DATE(created_at)
            ORDER BY day
            """
        )
        payload["requests_last_30_days"] = [
            {"day": str(row["day"]), "submitted": int(row["submitted"] or 0), "applied": int(row["applied"] or 0)}
            for row in rows
        ]
        return payload
