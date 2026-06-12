from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.sql_view_repo import SQLViewRepo


class ZonesViewsRepo(SQLViewRepo):
    """
    Read-model repository for Zones (GOLD V2.1)

    Backed by SQL view:
      - v_zones
    """

    def __init__(self, db: Session):
        super().__init__(db)

    @staticmethod
    def _normalize_zone_operational_summary(*, endpoint_count: int, reachable_count: int) -> str:
        if int(endpoint_count or 0) <= 0:
            return "attention"
        if int(reachable_count or 0) == int(endpoint_count or 0):
            return "healthy"
        return "attention"

    def _list_sql(self) -> str:
        return """
            SELECT
              v.*
            FROM v_zones v
            ORDER BY v.name
            """

    def _get_sql(self) -> str:
        return """
            SELECT
              v.*
            FROM v_zones v
            WHERE v.id = :id
            """

    # ============================================================
    # LIST
    # ============================================================

    def list(self) -> list[dict]:
        """
        List all zones (overview).

        Ordered by zone name.
        Used by:
        - Zones page
        - Zone selectors
        """
        rows = self._all_dicts(self._list_sql())
        return [self._attach_operational_summary(dict(row)) for row in rows]

    def get(self, zone_id: int) -> dict | None:
        row = self._one_dict(self._get_sql(), {"id": int(zone_id)})
        if row is None:
            return None
        return self._attach_operational_summary(dict(row))

    def _attach_operational_summary(self, zone: dict) -> dict:
        zone_id = int(zone.get("id") or 0)
        if zone_id <= 0:
            zone["operational_summary"] = "attention"
            return zone

        endpoints = self.list_console_endpoints(zone_id)
        endpoint_count = len(endpoints)
        reachable_count = sum(
            1
            for endpoint in endpoints
            if str(endpoint.get("operational_state") or "").strip().lower() == "reachable"
        )
        zone["operational_summary"] = self._normalize_zone_operational_summary(
            endpoint_count=endpoint_count,
            reachable_count=reachable_count,
        )
        return zone

    def list_console_endpoints(self, zone_id: int) -> list[dict]:
        rows = self._all_dicts(
            """
            SELECT
              id,
              name,
              endpoint_type,
              host,
              port,
              status,
              last_probe_status,
              last_probe_at,
              last_probe_message,
              bind_dn,
              bind_password_ref,
              bind_dn AS auth_username,
              bind_password_ref AS auth_secret_ref,
              is_active,
              zone_id
            FROM v_zone_console_endpoints
            WHERE zone_id = :zone_id
            ORDER BY name
            """,
            {"zone_id": int(zone_id)},
        )
        out: list[dict] = []
        for row in rows:
            payload = dict(row)
            is_active = payload.get("is_active")
            last_probe_status = str(payload.get("last_probe_status") or payload.get("status") or "").strip().lower()
            if is_active is False:
                payload["operational_state"] = "disabled"
            elif last_probe_status == "success":
                payload["operational_state"] = "reachable"
            elif last_probe_status == "running":
                payload["operational_state"] = "checking"
            elif last_probe_status == "failed":
                payload["operational_state"] = "unreachable"
            else:
                payload["operational_state"] = "unknown"
            out.append(payload)
        return out

    def list_console_roots(self, zone_id: int) -> list[dict]:
        return self._all_dicts(
            """
            SELECT
              id,
              name,
              root_path,
              status,
              storage_endpoint_id,
              zone_id
            FROM v_zone_console_roots
            WHERE zone_id = :zone_id
            ORDER BY name
            """,
            {"zone_id": int(zone_id)},
        )

    def list_console_access_profiles(self, zone_id: int) -> list[dict]:
        # Legacy console helper kept only while /zones/{id}/access-profiles still exists.
        return self._all_dicts(
            """
            SELECT
              id,
              code,
              name,
              permission,
              access_level_code,
              zone_id
            FROM v_zone_console_access_profiles
            WHERE zone_id = :zone_id
            ORDER BY code, name
            """,
            {"zone_id": int(zone_id)},
        )

    def get_effective_provisioning_policy(self, zone_id: int) -> dict | None:
        return self._one_dict(
            """
            SELECT *
            FROM v_zone_provisioning_policy_effective
            WHERE zone_id = :zone_id
            LIMIT 1
            """,
            {"zone_id": int(zone_id)},
        )

    def get_zone_provisioning_policy(self, zone_id: int) -> dict | None:
        return self._one_dict(
            """
            SELECT
              zone_id,
              enabled,
              policy_mode,
              ou_strategy,
              base_ou_dn,
              static_ou_dn,
              updated_at
            FROM zone_provisioning_policy
            WHERE zone_id = :zone_id
            LIMIT 1
            """,
            {"zone_id": int(zone_id)},
        )

    def list_zone_access_profiles(self, zone_id: int) -> list[dict]:
        return self._all_dicts(
            """
            SELECT
              zap.zone_id,
              zap.access_profile_id,
              zap.is_active,
              zap.created_at,
              ap.code,
              ap.name,
              ap.description,
              ap.permission,
              UPPER(COALESCE(NULLIF(ap.code, ''), NULLIF(ap.permission, ''), 'READ')) AS access_level_code
            FROM zone_access_profiles zap
            JOIN access_profiles ap ON ap.id = zap.access_profile_id
            WHERE zap.zone_id = :zone_id
              AND zap.is_active = 1
            ORDER BY ap.code, ap.name
            """,
            {"zone_id": int(zone_id)},
        )
