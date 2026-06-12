from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.repositories.sql_view_repo import SQLViewRepo


OPEN_STATUS = "open"
RESOLVED_STATUS = "resolved"
ACKNOWLEDGED_STATUS = "acknowledged"
FAILED_OR_PENDING_PROFILE_STATUSES = {"FAILED", "ERROR", "CANCELLED", "RETRYING", "RUNNING", "QUEUED", "NOT_CREATED"}
CREATED_PROFILE_STATUSES = {"CREATED", "SUCCEEDED", "PROVISIONED"}


class GovernanceAlertsRepo(SQLViewRepo):
    """Operational governance alert state.

    Alerts live in the business database because they are mutable operational
    state. The append-only logging DB remains the audit trail.
    """

    def __init__(self, db: Session):
        super().__init__(db)

    @staticmethod
    def _utcnow_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _parse_metadata(value: Any) -> Any:
        if value is None or isinstance(value, (dict, list)):
            return value
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8", errors="replace")
        if isinstance(value, str):
            text_value = value.strip()
            if not text_value:
                return None
            try:
                return json.loads(text_value)
            except Exception:
                return {"raw": text_value}
        return value

    @classmethod
    def _normalize_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row or {})
        out["metadata_json"] = cls._parse_metadata(out.get("metadata_json"))
        out["tone"] = "error" if str(out.get("severity") or "").lower() in {"critical", "high"} else "warning"
        return out

    def list_alerts(
        self,
        *,
        scope_type: str | None = None,
        scope_id: int | None = None,
        storage_root_id: int | None = None,
        storage_endpoint_id: int | None = None,
        status: str = OPEN_STATUS,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {
            "status": str(status or OPEN_STATUS).strip().lower(),
            "limit": max(1, min(int(limit or 500), 2000)),
        }

        if params["status"] != "all":
            clauses.append("LOWER(status) = :status")
        if scope_type:
            clauses.append("LOWER(scope_type) = :scope_type")
            params["scope_type"] = str(scope_type).strip().lower()
        if scope_id is not None:
            clauses.append("scope_id = :scope_id")
            params["scope_id"] = int(scope_id)
        if storage_root_id is not None:
            clauses.append("storage_root_id = :storage_root_id")
            params["storage_root_id"] = int(storage_root_id)
        if storage_endpoint_id is not None:
            clauses.append("storage_endpoint_id = :storage_endpoint_id")
            params["storage_endpoint_id"] = int(storage_endpoint_id)

        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._all(
            f"""
            SELECT
              id,
              alert_key,
              scope_type,
              scope_id,
              alert_type,
              severity,
              status,
              title,
              message,
              source_type,
              source_id,
              zone_id,
              storage_endpoint_id,
              storage_root_id,
              identity_source_id,
              correlation_id,
              first_seen_at,
              last_seen_at,
              resolved_at,
              acknowledged_at,
              acknowledged_by,
              metadata_json,
              created_at,
              updated_at
            FROM governance_alerts
            {where}
            ORDER BY
              CASE LOWER(severity)
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'warning' THEN 3
                ELSE 4
              END,
              last_seen_at DESC,
              id DESC
            LIMIT :limit
            """,
            params,
        )
        return [self._normalize_row(dict(row)) for row in rows]

    def list_for_storage_root(self, storage_root_id: int, *, status: str = OPEN_STATUS, limit: int = 200) -> list[dict[str, Any]]:
        return self.list_alerts(storage_root_id=int(storage_root_id), status=status, limit=limit)

    def _upsert_alert(self, alert: dict[str, Any]) -> None:
        metadata_json = alert.get("metadata_json")
        metadata_text = json.dumps(metadata_json, ensure_ascii=False, sort_keys=True) if metadata_json is not None else None
        now = self._utcnow_naive()
        params = {
            "alert_key": alert["alert_key"],
            "scope_type": alert["scope_type"],
            "scope_id": int(alert["scope_id"]),
            "alert_type": alert["alert_type"],
            "severity": alert.get("severity") or "warning",
            "title": alert["title"],
            "message": alert.get("message"),
            "source_type": alert.get("source_type"),
            "source_id": alert.get("source_id"),
            "zone_id": alert.get("zone_id"),
            "storage_endpoint_id": alert.get("storage_endpoint_id"),
            "storage_root_id": alert.get("storage_root_id"),
            "identity_source_id": alert.get("identity_source_id"),
            "correlation_id": alert.get("correlation_id"),
            "metadata_json": metadata_text,
            "now": now,
        }
        self.db.execute(
            text(
                """
                INSERT INTO governance_alerts (
                  alert_key,
                  scope_type,
                  scope_id,
                  alert_type,
                  severity,
                  status,
                  title,
                  message,
                  source_type,
                  source_id,
                  zone_id,
                  storage_endpoint_id,
                  storage_root_id,
                  identity_source_id,
                  correlation_id,
                  first_seen_at,
                  last_seen_at,
                  metadata_json
                )
                VALUES (
                  :alert_key,
                  :scope_type,
                  :scope_id,
                  :alert_type,
                  :severity,
                  'open',
                  :title,
                  :message,
                  :source_type,
                  :source_id,
                  :zone_id,
                  :storage_endpoint_id,
                  :storage_root_id,
                  :identity_source_id,
                  :correlation_id,
                  :now,
                  :now,
                  :metadata_json
                )
                ON DUPLICATE KEY UPDATE
                  severity = VALUES(severity),
                  status = 'open',
                  title = VALUES(title),
                  message = VALUES(message),
                  source_type = VALUES(source_type),
                  source_id = VALUES(source_id),
                  zone_id = VALUES(zone_id),
                  storage_endpoint_id = VALUES(storage_endpoint_id),
                  storage_root_id = VALUES(storage_root_id),
                  identity_source_id = VALUES(identity_source_id),
                  correlation_id = VALUES(correlation_id),
                  last_seen_at = VALUES(last_seen_at),
                  resolved_at = NULL,
                  metadata_json = VALUES(metadata_json)
                """
            ),
            params,
        )

    def _resolve_missing_storage_root_alerts(self, *, storage_root_id: int, active_keys: set[str]) -> None:
        if not active_keys:
            self.db.execute(
                text(
                    """
                    UPDATE governance_alerts
                    SET status = :resolved_status,
                        resolved_at = COALESCE(resolved_at, :now)
                    WHERE storage_root_id = :storage_root_id
                      AND status = :open_status
                    """
                ),
                {
                    "storage_root_id": int(storage_root_id),
                    "open_status": OPEN_STATUS,
                    "resolved_status": RESOLVED_STATUS,
                    "now": self._utcnow_naive(),
                },
            )
            return

        bind_keys = [f"key_{idx}" for idx, _ in enumerate(sorted(active_keys))]
        params: dict[str, Any] = {
            "storage_root_id": int(storage_root_id),
            "open_status": OPEN_STATUS,
            "resolved_status": RESOLVED_STATUS,
            "now": self._utcnow_naive(),
        }
        params.update({key: value for key, value in zip(bind_keys, sorted(active_keys))})
        in_clause = ", ".join(f":{key}" for key in bind_keys)

        self.db.execute(
            text(
                f"""
                UPDATE governance_alerts
                SET status = :resolved_status,
                    resolved_at = COALESCE(resolved_at, :now)
                WHERE storage_root_id = :storage_root_id
                  AND status = :open_status
                  AND alert_key NOT IN ({in_clause})
                """
            ),
            params,
        )

    def reconcile_storage_root(self, storage_root_id: int, *, commit: bool = False) -> list[dict[str, Any]]:
        root = self._one(
            """
            SELECT
              sr.id AS storage_root_id,
              sr.name AS storage_root_name,
              sr.root_path,
              sr.last_probe_status,
              sr.last_probe_at,
              sr.last_probe_message,
              sr.discovered_permissions_json,
              se.id AS storage_endpoint_id,
              se.name AS storage_endpoint_name,
              se.last_probe_status AS endpoint_probe_status,
              se.last_probe_at AS endpoint_probe_at,
              se.last_probe_message AS endpoint_probe_message,
              se.identity_source_id,
              z.id AS zone_id,
              z.name AS zone_name
            FROM storage_roots sr
            JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            JOIN zones z ON z.id = se.zone_id
            WHERE sr.id = :storage_root_id
              AND sr.deleted_at IS NULL
            LIMIT 1
            """,
            {"storage_root_id": int(storage_root_id)},
        )
        if not root:
            return []

        root_data = dict(root)
        root_id = int(root_data["storage_root_id"])
        endpoint_id = int(root_data["storage_endpoint_id"])
        zone_id = int(root_data["zone_id"])
        identity_source_id = root_data.get("identity_source_id")
        root_label = str(root_data.get("storage_root_name") or root_id)

        def base(alert_type: str) -> dict[str, Any]:
            return {
                "alert_key": f"storage_root:{root_id}:{alert_type}",
                "scope_type": "storage_root",
                "scope_id": root_id,
                "alert_type": alert_type,
                "zone_id": zone_id,
                "storage_endpoint_id": endpoint_id,
                "storage_root_id": root_id,
                "identity_source_id": int(identity_source_id) if identity_source_id else None,
            }

        alerts: list[dict[str, Any]] = []

        endpoint_status = str(root_data.get("endpoint_probe_status") or "").strip().lower()
        root_status = str(root_data.get("last_probe_status") or "").strip().lower()
        if endpoint_status == "failed":
            alerts.append(
                {
                    **base("endpoint_unreachable"),
                    "severity": "critical",
                    "title": "Endpoint unreachable",
                    "message": root_data.get("endpoint_probe_message") or root_data.get("last_probe_message"),
                    "source_type": "storage_endpoint_probe",
                    "source_id": str(endpoint_id),
                    "metadata_json": {
                        "storage_root_name": root_label,
                        "storage_endpoint_name": root_data.get("storage_endpoint_name"),
                        "endpoint_probe_status": endpoint_status,
                    },
                }
            )
        if root_status == "failed":
            alerts.append(
                {
                    **base("root_probe_failed"),
                    "severity": "critical",
                    "title": "Root probe failed",
                    "message": root_data.get("last_probe_message"),
                    "source_type": "storage_root_probe",
                    "source_id": str(root_id),
                    "metadata_json": {"storage_root_name": root_label, "last_probe_status": root_status},
                }
            )
        elif root_status == "running":
            alerts.append(
                {
                    **base("root_probe_running"),
                    "severity": "warning",
                    "title": "Root probe running",
                    "message": root_data.get("last_probe_message") or "Waiting for the latest probe result",
                    "source_type": "storage_root_probe",
                    "source_id": str(root_id),
                    "metadata_json": {"storage_root_name": root_label, "last_probe_status": root_status},
                }
            )
        elif root_status == "unknown":
            alerts.append(
                {
                    **base("root_probe_unknown"),
                    "severity": "warning",
                    "title": "Root probe unknown",
                    "message": root_data.get("last_probe_message") or "No recent root probe result",
                    "source_type": "storage_root_probe",
                    "source_id": str(root_id),
                    "metadata_json": {"storage_root_name": root_label, "last_probe_status": root_status},
                }
            )

        owner_rows = self._all(
            """
            SELECT LOWER(role) AS role, COUNT(*) AS count
            FROM storage_root_roles
            WHERE root_id = :storage_root_id
            GROUP BY LOWER(role)
            """,
            {"storage_root_id": root_id},
        )
        owner_counts = {str(row.get("role") or "").lower(): int(row.get("count") or 0) for row in owner_rows}
        if int(owner_counts.get("guardian") or 0) <= 0:
            alerts.append(
                {
                    **base("missing_guardian"),
                    "severity": "warning",
                    "title": "Guardian missing",
                    "message": "No guardian assigned",
                    "source_type": "governance_policy",
                    "source_id": str(root_id),
                    "metadata_json": {"storage_root_name": root_label, "role": "guardian"},
                }
            )
        profile_rows = self._all(
            """
            SELECT
              srap.id,
              UPPER(COALESCE(NULLIF(srap.access_level_code, ''), NULLIF(ap.code, ''), NULLIF(ap.permission, ''), 'READ')) AS access_level,
              srap.group_name,
              srap.group_external_id,
              UPPER(COALESCE(srap.status, 'NOT_CREATED')) AS status,
              srap.error_code,
              srap.error_message,
              srap.next_retry_at
            FROM storage_root_access_profiles srap
            LEFT JOIN access_profiles ap ON ap.id = srap.access_profile_id
            WHERE srap.storage_root_id = :storage_root_id
              AND COALESCE(srap.active, 1) = 1
              AND srap.deleted_at IS NULL
            ORDER BY access_level, srap.id
            """,
            {"storage_root_id": root_id},
        )
        raw_acl_payload = root_data.get("discovered_permissions_json")
        if isinstance(raw_acl_payload, str):
            try:
                raw_acl_payload = json.loads(raw_acl_payload)
            except (TypeError, ValueError):
                raw_acl_payload = {}
        if not isinstance(raw_acl_payload, dict):
            raw_acl_payload = {}
        acl_permissions = raw_acl_payload.get("permissions")
        if not isinstance(acl_permissions, list):
            acl_permissions = []

        def normalize_principal(value: Any) -> str:
            raw = str(value or "").strip().replace("/", "\\").lower()
            chunks = [chunk for chunk in raw.split("\\") if chunk]
            return chunks[-1] if chunks else raw

        acl_by_name = {
            normalize_principal(permission.get("principal"))
            for permission in acl_permissions
            if isinstance(permission, dict) and normalize_principal(permission.get("principal"))
        }
        expected_groups: set[str] = set()
        if len(profile_rows) <= 0:
            alerts.append(
                {
                    **base("missing_access_profile"),
                    "severity": "warning",
                    "title": "Access profile missing",
                    "message": "No access profile linked to this storage root",
                    "source_type": "governance_policy",
                    "source_id": str(root_id),
                    "metadata_json": {"storage_root_name": root_label},
                }
            )
        for row in profile_rows:
            profile_status = str(row.get("status") or "").strip().upper()
            group_external_id = str(row.get("group_external_id") or "").strip()
            access_level = str(row.get("access_level") or "READ").strip().upper()
            group_name = str(row.get("group_name") or "").strip() or None
            normalized_group = normalize_principal(group_name)
            if normalized_group:
                expected_groups.add(normalized_group)
            if profile_status in CREATED_PROFILE_STATUSES:
                pass
            elif profile_status not in FAILED_OR_PENDING_PROFILE_STATUSES and group_external_id:
                pass
            else:
                is_pending = profile_status in {"RETRYING", "RUNNING", "QUEUED"}
                alert_type = f"ad_group_{access_level.lower()}_{'pending' if is_pending else 'not_created'}"
                profile_id = int(row.get("id") or 0)
                alert = {
                    **base(alert_type),
                    "alert_key": f"storage_root:{root_id}:{alert_type}:{profile_id}",
                    "severity": "warning" if is_pending else "high",
                    "title": f"{access_level} group {'pending' if is_pending else 'not created'}",
                    "message": row.get("error_message") or (
                        f"{group_name} · {profile_status}" if group_name else "No AD group linked"
                    ),
                    "source_type": "storage_root_access_profile",
                    "source_id": str(profile_id),
                    "metadata_json": {
                        "storage_root_name": root_label,
                        "access_level": access_level,
                        "group_name": group_name,
                        "profile_status": profile_status,
                        "error_code": row.get("error_code"),
                        "next_retry_at": str(row.get("next_retry_at")) if row.get("next_retry_at") else None,
                    },
                }
                alerts.append(alert)

            if acl_permissions and normalized_group and normalized_group not in acl_by_name:
                profile_id = int(row.get("id") or 0)
                alerts.append(
                    {
                        **base("acl_profile_missing"),
                        "alert_key": f"storage_root:{root_id}:acl_profile_missing:{profile_id}",
                        "severity": "high",
                        "title": f"{access_level} group missing from filesystem ACL",
                        "message": f"{group_name} is expected by policy but was not found in the latest ACL scan",
                        "source_type": "acl_scan",
                        "source_id": str(raw_acl_payload.get("probe_job_id") or root_id),
                        "metadata_json": {
                            "storage_root_name": root_label,
                            "access_level": access_level,
                            "group_name": group_name,
                            "scan_source": raw_acl_payload.get("source"),
                            "scan_probe_job_id": raw_acl_payload.get("probe_job_id"),
                            "scan_permissions_count": len(acl_permissions),
                        },
                    }
                )

        for permission in acl_permissions:
            if not isinstance(permission, dict):
                continue
            normalized_principal = normalize_principal(permission.get("principal"))
            if not normalized_principal or normalized_principal in expected_groups:
                continue
            principal = str(permission.get("principal") or "").strip()
            if not principal:
                continue
            alerts.append(
                {
                    **base("acl_principal_not_governed"),
                    "alert_key": f"storage_root:{root_id}:acl_principal_not_governed:{normalized_principal}",
                    "severity": "warning",
                    "title": "Filesystem ACL not governed",
                    "message": f"{principal} is present in the filesystem ACL but is not linked to an access profile",
                    "source_type": "acl_scan",
                    "source_id": str(raw_acl_payload.get("probe_job_id") or root_id),
                    "metadata_json": {
                        "storage_root_name": root_label,
                        "principal": principal,
                        "access_level": permission.get("access_level"),
                        "raw": permission.get("raw"),
                        "scan_probe_job_id": raw_acl_payload.get("probe_job_id"),
                    },
                }
            )

        pending_row = self._one(
            """
            SELECT COUNT(*) AS count
            FROM v_access_requests
            WHERE LOWER(COALESCE(status, '')) = 'pending'
              AND storage_root_id = :storage_root_id
            """,
            {"storage_root_id": root_id},
        )
        pending_count = int((pending_row or {}).get("count") or 0)
        if pending_count > 0:
            alerts.append(
                {
                    **base("pending_access_validation"),
                    "severity": "warning",
                    "title": f"{pending_count} access request{'s' if pending_count != 1 else ''} pending",
                    "message": "Validation required",
                    "source_type": "access_request",
                    "source_id": str(root_id),
                    "metadata_json": {"storage_root_name": root_label, "pending_count": pending_count},
                }
            )

        active_keys = {alert["alert_key"] for alert in alerts}
        for alert in alerts:
            self._upsert_alert(alert)
        self._resolve_missing_storage_root_alerts(storage_root_id=root_id, active_keys=active_keys)

        if commit:
            self.db.commit()

        return self.list_for_storage_root(root_id)

    def reconcile_all_storage_roots(self, *, commit: bool = False) -> int:
        rows = self._all(
            "SELECT id FROM storage_roots WHERE deleted_at IS NULL ORDER BY id",
            {},
        )
        count = 0
        for row in rows:
            self.reconcile_storage_root(int(row.get("id")), commit=False)
            count += 1
        if commit:
            self.db.commit()
        return count
