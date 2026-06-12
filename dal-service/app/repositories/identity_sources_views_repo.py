from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.repositories.sql_view_repo import SQLViewRepo


class IdentitySourcesViewsRepo(SQLViewRepo):
    """Read-model repository for identity sources SQL views."""

    def __init__(self, db: Session):
        super().__init__(db)

    @staticmethod
    def empty_latest_snapshot_meta() -> dict[str, str | int | None]:
        return {
            "last_snapshot_at": None,
            "last_snapshot_status": None,
            "last_snapshot_version": None,
            "last_snapshot_users_count": None,
            "last_snapshot_groups_count": None,
            "last_snapshot_memberships_count": None,
            "last_snapshot_objects_count": None,
        }

    @staticmethod
    def _normalize_latest_snapshot_meta(row: dict[str, Any] | None) -> dict[str, str | int | None]:
        if not row:
            return IdentitySourcesViewsRepo.empty_latest_snapshot_meta()

        raw_ts = row.get("last_snapshot_at")
        last_snapshot_at = raw_ts.isoformat() if getattr(raw_ts, "isoformat", None) else None

        users_count = int(row.get("last_snapshot_users_count") or 0)
        groups_count = int(row.get("last_snapshot_groups_count") or 0)
        memberships_count = int(row.get("last_snapshot_memberships_count") or 0)
        objects_count = int(row.get("last_snapshot_objects_count") or (users_count + groups_count))

        return {
            "last_snapshot_at": last_snapshot_at,
            "last_snapshot_status": str(row.get("last_snapshot_status") or "").strip() or None,
            "last_snapshot_version": int(row.get("last_snapshot_version") or 0) or None,
            "last_snapshot_users_count": users_count,
            "last_snapshot_groups_count": groups_count,
            "last_snapshot_memberships_count": memberships_count,
            "last_snapshot_objects_count": objects_count,
        }

    def list_latest_snapshot_meta_by_source(self) -> dict[int, dict[str, str | int | None]]:
        rows = self._all_dicts(
            """
            SELECT
                identity_source_id,
                last_snapshot_at,
                last_snapshot_status,
                last_snapshot_version,
                last_snapshot_users_count,
                last_snapshot_groups_count,
                last_snapshot_memberships_count,
                last_snapshot_objects_count
            FROM v_identity_source_latest_snapshot
            """
        )

        out: dict[int, dict[str, str | int | None]] = {}
        for row in rows:
            source_id = int(row.get("identity_source_id") or 0)
            if source_id <= 0:
                continue
            out[source_id] = self._normalize_latest_snapshot_meta(row)
        return out

    def get_latest_snapshot_meta(self, source_id: int) -> dict[str, str | int | None]:
        source_key = int(source_id)
        if source_key <= 0:
            return self.empty_latest_snapshot_meta()

        rows_map = self.list_latest_snapshot_meta_by_source()
        return rows_map.get(source_key, self.empty_latest_snapshot_meta())
