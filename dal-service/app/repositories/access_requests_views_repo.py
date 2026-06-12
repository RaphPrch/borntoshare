from __future__ import annotations

from typing import Any, List, Optional
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text, bindparam
from sqlalchemy.exc import SQLAlchemyError

from app.core.sql import to_dicts
from app.services.activity_bridge import list_activity_by_target
from app.services.naming_policy import resolve_group_name


class AccessRequestsReadModelContractError(RuntimeError):
    """Raised when mandatory read-model SQL objects are unavailable at runtime."""


class AccessRequestsViewsRepo:
    """
    READ-ONLY repository for Access Requests (GOLD).

    Backed by SQL views:
      - v_access_requests                  (LIST / TABLE)
      - v_access_request_timeline          (DETAIL / TIMELINE)
      - v_access_requests_expiring_soon    (DASHBOARD / TTL)

    Rules:
      - NO writes
      - NO ORM models
      - NO business logic
      - NO RBAC filtering (handled by caller / frontend BFF)
    """

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _missing_view_error(*, view_name: str, operation: str) -> AccessRequestsReadModelContractError:
        return AccessRequestsReadModelContractError(
            "Access requests read-model contract violation: "
            f"missing SQL view '{view_name}' required by operation '{operation}'. "
            "Apply Wizard SQL schema/views packs before starting DAL."
        )

    # ============================================================
    # LIST — STATUS (GLOBAL / UI TABLE)
    # ============================================================

    def _risk(self, snapshot_count: int | None) -> str | None:
        if snapshot_count and snapshot_count >= 50:
            return "high"
        if snapshot_count and snapshot_count >= 10:
            return "medium"
        return "low" if snapshot_count is not None else None

    def _extract_principal_display(self, principal: Any) -> str | None:
        payload = principal
        if isinstance(payload, str):
            raw = payload.strip()
            if not raw:
                return None
            try:
                payload = json.loads(raw)
            except Exception:
                return raw

        if not isinstance(payload, dict):
            return None

        for key in ("display_name", "username", "dn", "external_id", "id"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        return None

    def _created_at_sort_key(self, value: Any) -> tuple[int, datetime]:
        """Build a stable sort key for timeline events with mixed timestamp types."""
        if isinstance(value, datetime):
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return (0, dt)

        if isinstance(value, str):
            raw = value.strip()
            if raw:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    return (0, dt)
                except Exception:
                    pass

        return (1, datetime.max.replace(tzinfo=timezone.utc))

    def _fetch_requests_snapshot(self, request_ids: list[int]) -> dict[int, dict[str, Any]]:
        ids = [int(x) for x in request_ids if int(x) > 0]
        if not ids:
            return {}

        sql = text(
            """
            SELECT
                ar.id AS request_id,
                ar.requested_principal_json AS requested_principal_json,
                ar.decision_comment AS justification,
                ari.target_type AS target_type,
                ari.target_id AS target_id,
                ari.permission AS permission,
                ari.expires_at AS expires_at,
                sr.id AS storage_root_id,
                sr.name AS storage_root_name,
                sr.root_path AS target_path
            FROM access_requests ar
            LEFT JOIN access_request_items ari ON ari.id = (
                SELECT x.id
                FROM access_request_items x
                WHERE x.access_request_id = ar.id
                ORDER BY x.id ASC
                LIMIT 1
            )
            LEFT JOIN storage_roots sr ON (
                LOWER(COALESCE(ari.target_type, '')) = 'storage_root'
                AND sr.id = ari.target_id
            )
            WHERE ar.id IN :ids
            """
        ).bindparams(bindparam("ids", expanding=True))

        rows = self.db.execute(sql, {"ids": ids}).mappings().all()
        return {int(row["request_id"]): dict(row) for row in rows if row.get("request_id") is not None}

    def _enrich_row(self, row: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any]:
        if not snapshot:
            return row

        merged = dict(row)

        principal_display = self._extract_principal_display(snapshot.get("requested_principal_json"))
        if not merged.get("requested_for_display") and principal_display:
            merged["requested_for_display"] = principal_display

        if not merged.get("requested_principal_json") and snapshot.get("requested_principal_json") is not None:
            merged["requested_principal_json"] = snapshot.get("requested_principal_json")

        if not merged.get("access_profile_name") and snapshot.get("permission"):
            merged["access_profile_name"] = snapshot.get("permission")

        if not merged.get("scope_type") and snapshot.get("target_type"):
            merged["scope_type"] = snapshot.get("target_type")

        if not merged.get("target_path") and snapshot.get("target_path"):
            merged["target_path"] = snapshot.get("target_path")

        if not merged.get("storage_root_name") and snapshot.get("storage_root_name"):
            merged["storage_root_name"] = snapshot.get("storage_root_name")

        if not merged.get("scope_display"):
            if snapshot.get("storage_root_name"):
                merged["scope_display"] = snapshot.get("storage_root_name")
            elif snapshot.get("target_type") and snapshot.get("target_id"):
                merged["scope_display"] = f"/{snapshot.get('target_type')}/{snapshot.get('target_id')}"

        if not merged.get("expires_at") and snapshot.get("expires_at"):
            merged["expires_at"] = snapshot.get("expires_at")

        if not merged.get("justification") and snapshot.get("justification"):
            merged["justification"] = snapshot.get("justification")

        return merged

    def _fetch_guardian_names_by_root(self, storage_root_ids: list[int]) -> dict[int, str]:
        ids = [int(x) for x in storage_root_ids if int(x) > 0]
        if not ids:
            return {}

        sql_roles = text(
            """
            SELECT
              srr.root_id AS storage_root_id,
              GROUP_CONCAT(
                COALESCE(i.display_name, i.username, i.email, CONCAT('Identity #', srr.identity_id))
                ORDER BY COALESCE(i.display_name, i.username, i.email, CAST(srr.identity_id AS CHAR))
                SEPARATOR ', '
              ) AS guardian_name
            FROM storage_root_roles srr
            LEFT JOIN identities i ON i.id = srr.identity_id
            WHERE srr.root_id IN :ids
              AND LOWER(srr.role) = 'guardian'
            GROUP BY srr.root_id
            """
        ).bindparams(bindparam("ids", expanding=True))

        rows = self.db.execute(sql_roles, {"ids": ids}).mappings().all()
        return {
            int(r.get("storage_root_id") or 0): str(r.get("guardian_name") or "").strip()
            for r in rows
            if int(r.get("storage_root_id") or 0) > 0 and str(r.get("guardian_name") or "").strip()
        }

    def list(
        self,
        *,
        status: str | None = None,
        request_id: int | None = None,
        my_action: bool = False,
        overdue_only: bool = False,
        high_impact: bool = False,
        q: str | None = None,
    ) -> List[dict]:
        """
        List access requests with V1++ fields.

        SQL view:
          - v_access_requests
        """
        sql = """
            SELECT *
            FROM v_access_requests
            WHERE (:status IS NULL OR status = :status)
              AND (:request_id IS NULL OR request_id = :request_id)
              AND (:q IS NULL OR (request_code LIKE :q OR requested_for_display LIKE :q))
            ORDER BY created_at DESC
            LIMIT 200
        """
        params: dict[str, Any] = {
            "status": status,
            "request_id": int(request_id) if request_id is not None else None,
            "q": f"%{q}%" if q else None,
        }

        rows = []
        mappings = self.db.execute(text(sql), params).mappings()

        for m in mappings:
            snap_cnt = m.get("impact_snapshot_users_count") or 0
            if overdue_only:
                continue
            if high_impact and snap_cnt < 10:
                continue
            row = dict(m)
            row["overdue"] = False
            row["risk"] = self._risk(snap_cnt)
            rows.append(row)

        snapshots = self._fetch_requests_snapshot(
            [int(r.get("request_id") or 0) for r in rows if r.get("request_id") is not None]
        )
        rows = [
            self._enrich_row(r, snapshots.get(int(r.get("request_id") or 0)))
            for r in rows
        ]

        guardian_names = self._fetch_guardian_names_by_root(
            [int(r.get("storage_root_id") or 0) for r in rows if int(r.get("storage_root_id") or 0) > 0]
        )
        for row in rows:
            root_id = int(row.get("storage_root_id") or 0)
            if root_id > 0:
                row["guardian_name"] = guardian_names.get(root_id)

        if my_action:
            return rows

        return rows

    # ============================================================
    # GET ONE — OVERVIEW (DETAIL PANEL)
    # ============================================================

    def get_details(self, access_request_id: int) -> Optional[dict]:
        sql = text("""
            SELECT *
            FROM v_access_requests
            WHERE request_id = :id
        """)
        try:
            base = (
                self.db.execute(sql, {"id": int(access_request_id)})
                .mappings()
                .first()
            )
        except SQLAlchemyError as exc:
            raise self._missing_view_error(
                view_name="v_access_requests",
                operation="get_access_request_details",
            ) from exc

        if not base:
            return None

        snapshot = self._fetch_requests_snapshot([int(access_request_id)]).get(int(access_request_id))
        base = self._enrich_row(dict(base), snapshot)

        try:
            timeline = self.db.execute(
                text("""
                    SELECT *
                    FROM v_access_request_timeline
                    WHERE request_id = :id
                    ORDER BY created_at ASC
                """),
                {"id": int(access_request_id)},
            ).mappings().all()
        except SQLAlchemyError as exc:
            raise self._missing_view_error(
                view_name="v_access_request_timeline",
                operation="get_access_request_details",
            ) from exc

        try:
            activity = list_activity_by_target(
                target_type="access_request",
                target_id=int(access_request_id),
                limit=500,
            )
            activity.sort(key=lambda a: self._created_at_sort_key(a.get("created_at")))
        except Exception:
            activity = []

        try:
            provisionings = self.db.execute(
                text("""
                    SELECT *
                    FROM v_access_request_provisioning
                    WHERE access_request_id = :id
                    ORDER BY created_at ASC
                """),
                {"id": int(access_request_id)},
            ).mappings().all()
        except SQLAlchemyError as exc:
            raise self._missing_view_error(
                view_name="v_access_request_provisioning",
                operation="get_access_request_details",
            ) from exc

        timeline_rows = to_dicts(timeline)
        for a in activity:
            action = (a.get("action") or "")
            event_type = "event"
            if action.endswith(".enforce") or action.endswith("enforce") or action.startswith("acl.apply"):
                event_type = "enforce"
            elif action.endswith(".revoke") or action.endswith("revoke"):
                event_type = "revoke"
            timeline_rows.append(
                {
                    "event_type": event_type,
                    "actor_display": a.get("actor_display") or "system",
                    "message": str(a.get("context_json")) if a.get("context_json") else None,
                    "created_at": a.get("created_at"),
                }
            )

        timeline_rows.sort(key=lambda e: self._created_at_sort_key(e.get("created_at")))

        # ------------------------------------------------------------
        # Extra governance/source/group fields for Access Request detail UI
        # (best effort, fully DB-backed)
        # ------------------------------------------------------------
        storage_root_id = int(base.get("storage_root_id") or 0)
        permission_raw = str(base.get("access_profile_name") or "").strip().lower()
        access_level_code = "WRITE" if permission_raw in {"write", "contribution", "modify", "rw", "read_write", "read-write"} else "READ"

        context_row: dict[str, Any] = {}
        if storage_root_id > 0:
            try:
                context_row = dict(
                    (
                        self.db.execute(
                            text(
                                """
                                SELECT
                                  z.id AS zone_id,
                                  z.name AS zone_name,
                                  z.classification AS sensitivity_zone,
                                  ids.id AS identity_source_id,
                                  ids.name AS identity_source_name,
                                  ids.default_group_ou_dn,
                                  zpp.policy_mode,
                                  zpp.base_ou_dn,
                                  zpp.enabled AS policy_enabled
                                FROM storage_roots sr
                                LEFT JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
                                LEFT JOIN zones z ON z.id = se.zone_id
                                LEFT JOIN identity_sources ids ON ids.id = se.identity_source_id
                                LEFT JOIN zone_provisioning_policy zpp ON zpp.zone_id = z.id
                                WHERE sr.id = :storage_root_id
                                LIMIT 1
                                """
                            ),
                            {"storage_root_id": storage_root_id},
                        )
                        .mappings()
                        .first()
                    )
                    or {}
                )
            except Exception:
                context_row = {}

        group_name = None
        if storage_root_id > 0:
            try:
                group_row = (
                    self.db.execute(
                        text(
                            """
                            SELECT
                              COALESCE(NULLIF(srap.group_name, '')) AS group_name
                            FROM storage_root_access_profiles srap
                            WHERE srap.storage_root_id = :storage_root_id
                              AND UPPER(COALESCE(srap.access_level_code, 'READ')) = :access_level_code
                              AND srap.deleted_at IS NULL
                            ORDER BY srap.id DESC
                            LIMIT 1
                            """
                        ),
                        {
                            "storage_root_id": storage_root_id,
                            "access_level_code": access_level_code,
                        },
                    )
                    .mappings()
                    .first()
                )
                group_name = str((group_row or {}).get("group_name") or "").strip() or None
            except Exception:
                group_name = None

        expected_group_name = None
        if storage_root_id > 0:
            try:
                zone_ref = (context_row or {}).get("zone_id") or (context_row or {}).get("zone_name")
                storage_path = str(base.get("target_path") or base.get("scope_display") or "")
                naming = resolve_group_name(
                    self.db,
                    zone_ref=zone_ref,
                    storage_root_path=storage_path,
                    perm=str(access_level_code or "READ"),
                    profile=str(base.get("access_profile_name") or "").strip() or None,
                )
                expected_group_name = str((naming or {}).get("samAccountName") or "").strip() or None
            except Exception:
                expected_group_name = None

        guardian_names = self._fetch_guardian_names_by_root([storage_root_id]) if storage_root_id > 0 else {}
        guardian_name = guardian_names.get(storage_root_id)

        ttl_enforced = bool(base.get("expires_at"))
        justification_required = bool(str(base.get("justification") or "").strip())

        risk_level = "low"
        if access_level_code == "WRITE":
            risk_level = "medium"
        if str(base.get("status") or "").strip().lower() in {"rejected", "revoked"}:
            risk_level = "high"

        return {
            "request_id": base["request_id"],
            "request_code": base["request_code"],
            "status": base.get("status"),
            "created_at": base.get("created_at"),
            "updated_at": base.get("updated_at"),
            "scope_type": base.get("scope_type"),
            "scope_display": base.get("scope_display"),
            "target_path": base.get("target_path"),
            "storage_root_id": base.get("storage_root_id"),
            "storage_root_name": base.get("storage_root_name"),
            "access_profile_name": base.get("access_profile_name"),
            "expires_at": base.get("expires_at"),
            "requested_for_display": base.get("requested_for_display"),
            "requested_principal_json": base.get("requested_principal_json"),
            "requested_principal_type": base.get("requested_principal_type"),
            "requested_principal_dn": base.get("requested_principal_dn"),
            "requested_principal_external_id": base.get("requested_principal_external_id"),
            "latest_execution_status": base.get("latest_execution_status"),
            "latest_execution_job_id": base.get("latest_execution_job_id"),
            "justification": base.get("justification"),
            "justification_required": justification_required,
            "ttl_enforced": ttl_enforced,
            "sensitivity_zone": (context_row or {}).get("sensitivity_zone") or (context_row or {}).get("zone_name"),
            "zone_name": (context_row or {}).get("zone_name"),
            "zone": (context_row or {}).get("zone_name"),
            "storage_root_zone": (context_row or {}).get("zone_name"),
            "risk_level": risk_level,
            "impact_level": risk_level,
            "risk": {"level": risk_level},
            "ad_group": group_name,
            "expected_ad_group": expected_group_name,
            "expected_group_name": expected_group_name,
            "applied_via_group": group_name,
            "principal_group": group_name,
            "grant_group": group_name,
            "group_name": group_name,
            "guardian_name": guardian_name,
            "source_snapshot": (context_row or {}).get("identity_source_name"),
            "snapshot_source": (context_row or {}).get("identity_source_name"),
            "snapshot": {
                "name": (context_row or {}).get("identity_source_name"),
            },
            "source_name": (context_row or {}).get("identity_source_name"),
            "source_id": (context_row or {}).get("identity_source_id"),
            "governance": {
                "justification_required": justification_required,
                "ttl_enforced": ttl_enforced,
                "zone": (context_row or {}).get("zone_name"),
                "risk_level": risk_level,
            },
            "policy": {
                "justification_required": justification_required,
                "ttl_enforced": ttl_enforced,
            },
            "timeline": timeline_rows,
            "provisioning": to_dicts(provisionings),
        }

    # ============================================================
    # LIST — EXPIRING SOON (DASHBOARD / TTL)
    # ============================================================

    def list_expiring_soon(self) -> List[dict]:
        """
        List approved access requests expiring soon.

        Used by:
          - Dashboard (alerts / KPI)
          - Future notifications

        SQL view:
          - v_access_requests_expiring_soon
        """
        sql = text("""
            SELECT
              access_request_id,
              requester_id,
              username              AS requester_username,
              storage_root_id,
              storage_root_name,
              expires_at,
              hours_remaining
            FROM v_access_requests_expiring_soon
            ORDER BY hours_remaining ASC
        """)

        rows = self.db.execute(sql).mappings().all()
        return to_dicts(rows)

    def counts_by_status(
        self,
        *,
        my_action: bool = False,
        overdue_only: bool = False,
        high_impact: bool = False,
        q: str | None = None,
    ) -> dict[str, int]:
        rows = self.list(
            status=None,
            my_action=my_action,
            overdue_only=overdue_only,
            high_impact=high_impact,
            q=q,
        )
        counts: dict[str, int] = {
            "pending": 0,
            "approved": 0,
            "enforced": 0,
            "revoked": 0,
            "rejected": 0,
        }
        for row in rows:
            st = str(row.get("status") or "").lower().strip()
            if st in counts:
                counts[st] += 1
        return counts
