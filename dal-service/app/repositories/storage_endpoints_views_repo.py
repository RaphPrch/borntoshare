from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.sql_view_repo import SQLViewRepo


class StorageEndpointsViewsRepo(SQLViewRepo):
    """
    Read-model repository for Storage Endpoints (v4 minimal)

    STRICTLY backed by Wizard-UI SQL views:
      - v_storage_endpoints_context    (list / sidebar / tree)
      - v_storage_endpoint_detail      (single endpoint overview)
    """

    def __init__(self, db: Session):
        super().__init__(db)

    def _load_pending_root_counts_by_endpoint(self) -> dict[int, int]:
        rows = self._all_dicts(
            """
            SELECT
              storage_endpoint_id,
              COUNT(*) AS pending_requests_count
            FROM v_access_requests
            WHERE LOWER(COALESCE(status, '')) = 'pending'
              AND storage_endpoint_id IS NOT NULL
            GROUP BY storage_endpoint_id
            """
        )
        return {
            int(row.get("storage_endpoint_id") or 0): int(row.get("pending_requests_count") or 0)
            for row in rows
            if int(row.get("storage_endpoint_id") or 0) > 0
        }

    @staticmethod
    def _read_backend_pending_requests_count(row: dict[str, object] | None) -> int | None:
        payload = dict(row or {})
        raw = payload.get("pending_requests_count")
        if raw in (None, ""):
            return None
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_operational_state(*, is_active: object, last_probe_status: object) -> str:
        if is_active is False:
            return "disabled"

        probe = str(last_probe_status or "").strip().lower()
        if probe == "success":
            return "reachable"
        if probe == "running":
            return "checking"
        if probe == "failed":
            return "unreachable"
        return "unknown"

    # ============================================================
    # CONTEXT (LIST / SIDEBAR / WIZARD)
    # ============================================================

    def list_context(
        self,
        *,
        zone_id: int | None = None,
        endpoint_type: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """
        List storage endpoints for sidebar / tree.

        Filters are optional and UI-driven.
        """
        where: list[str] = []
        params: dict = {}

        if zone_id is not None:
            where.append("zone_id = :zone_id")
            params["zone_id"] = int(zone_id)

        if endpoint_type:
            where.append("LOWER(storage_endpoint_type) = LOWER(:type)")
            params["type"] = str(endpoint_type)

        if status:
            where.append("LOWER(status) = LOWER(:status)")
            params["status"] = str(status)

        sql = """
            SELECT *
            FROM v_storage_endpoints_context
        """

        if where:
            sql += "\nWHERE " + " AND ".join(where)

        sql += "\nORDER BY zone_name, storage_endpoint_name"

        rows = self._all(sql, params)
        pending_counts = self._load_pending_root_counts_by_endpoint()
        out: list[dict] = []
        for row in rows:
            payload = dict(row)
            payload["operational_state"] = self._normalize_operational_state(
                is_active=payload.get("is_active"),
                last_probe_status=payload.get("last_probe_status") or payload.get("status"),
            )
            backend_pending = self._read_backend_pending_requests_count(payload)
            if backend_pending is not None:
                payload["pending_requests_count"] = backend_pending
            else:
                payload["pending_requests_count"] = int(
                    pending_counts.get(int(payload.get("storage_endpoint_id") or payload.get("id") or 0), 0)
                )
            out.append(payload)
        return out

    # Standard name (UI list)
    def list(self, **kwargs) -> list[dict]:
        return self.list_context(**kwargs)

    # ============================================================
    # OVERVIEW — LIST (UI)
    # ============================================================

    def list_overview(self) -> list[dict]:
        """
        List storage endpoints for UI pages.

        Wizard-UI does not define `v_storage_endpoints_overview`.
        For V1, the UI list is backed by `v_storage_endpoints_context`.
        """
        sql = """
            SELECT *
            FROM v_storage_endpoints_context
            ORDER BY zone_name, storage_endpoint_name
        """

        return self._all(sql)

    # ============================================================
    # OVERVIEW — SINGLE (DETAIL / POLLING)
    # ============================================================

    def get_overview(
        self,
        storage_endpoint_id: int,
    ) -> dict | None:
        """
        Detailed read-model for one storage endpoint.

        Used by:
          - detail panel
          - polling (/overview)
          - UI status refresh
        """
        row = self._one_dict(
            """
            SELECT *
            FROM v_storage_endpoint_detail
            WHERE id = :id
            """,
            {"id": int(storage_endpoint_id)},
        )
        if row is None:
            return None

        payload = dict(row)
        payload["operational_state"] = self._normalize_operational_state(
            is_active=payload.get("is_active"),
            last_probe_status=payload.get("last_probe_status") or payload.get("status"),
        )
        if payload.get("roots_count") in (None, ""):
            payload["roots_count"] = int(len(self.list_console_roots(storage_endpoint_id)))
        backend_pending = self._read_backend_pending_requests_count(payload)
        if backend_pending is not None:
            payload["pending_requests_count"] = backend_pending
        else:
            payload["pending_requests_count"] = int(
                self._load_pending_root_counts_by_endpoint().get(int(storage_endpoint_id), 0)
            )
        return payload

    # Standard name
    def get(self, storage_endpoint_id: int) -> dict | None:
        return self.get_overview(storage_endpoint_id)

    def list_console_roots(self, storage_endpoint_id: int) -> list[dict]:
        return self._all_dicts(
            """
            SELECT
              id,
              name,
              status,
              zone_id,
              zone_name,
              storage_endpoint_id
            FROM v_storage_endpoint_console_roots
            WHERE storage_endpoint_id = :storage_endpoint_id
            ORDER BY name
            """,
            {"storage_endpoint_id": int(storage_endpoint_id)},
        )

    def get_console(self, storage_endpoint_id: int) -> dict | None:
        endpoint = self.get_overview(storage_endpoint_id)
        if endpoint is None or not isinstance(endpoint, dict):
            return None

        roots = self.list_console_roots(storage_endpoint_id)
        return {
            "endpoint": endpoint,
            "storageRoots": roots,
            "kpis": {
                "roots_count": int(endpoint.get("roots_count") or len(roots)),
            },
        }

    def get_effective_provisioning_policy(self, storage_endpoint_id: int) -> dict | None:
        return self._one_dict(
            """
            SELECT *
            FROM v_storage_endpoint_provisioning_effective
            WHERE storage_endpoint_id = :storage_endpoint_id
            LIMIT 1
            """,
            {"storage_endpoint_id": int(storage_endpoint_id)},
        )
