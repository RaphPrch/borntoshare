from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.data.repositories.sql_view_repo import SQLViewRepo
from app.core.values import utcnow_naive


OPEN_STATUS = "open"
RESOLVED_STATUS = "resolved"
ACKNOWLEDGED_STATUS = "acknowledged"


class GovernanceAlertsRepo(SQLViewRepo):
    """Operational governance alert state.

    Alerts live in the business database because they are mutable operational
    state. The append-only logging DB remains the audit trail.
    """

    def __init__(self, db: Session):
        super().__init__(db)

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

    def get_alert(self, alert_id: int) -> dict[str, Any] | None:
        return self._one_dict(
            "SELECT id, title, alert_type, severity, status FROM governance_alerts WHERE id = :id", {"id": int(alert_id)}
        )

    def set_status(self, alert_id: int, status: str, *, actor_id: int | None = None) -> None:
        """Operator action: acknowledge (still active, known) or resolve an alert."""
        now = utcnow_naive()
        if status == ACKNOWLEDGED_STATUS:
            sql = """
                UPDATE governance_alerts
                SET status = :status, acknowledged_at = :now, acknowledged_by = :actor_id, updated_at = :now
                WHERE id = :id
            """
        elif status == RESOLVED_STATUS:
            sql = """
                UPDATE governance_alerts
                SET status = :status, resolved_at = :now, updated_at = :now
                WHERE id = :id
            """
        else:
            raise ValueError(f"unsupported alert status: {status}")
        self.db.execute(text(sql), {"status": status, "now": now, "actor_id": actor_id, "id": int(alert_id)})
        self.db.commit()

    def _upsert_alert(self, alert: dict[str, Any]) -> None:
        metadata_json = alert.get("metadata_json")
        metadata_text = json.dumps(metadata_json, ensure_ascii=False, sort_keys=True) if metadata_json is not None else None
        now = utcnow_naive()
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
                  status = IF(status = 'acknowledged', 'acknowledged', 'open'),
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
                    "now": utcnow_naive(),
                },
            )
            return

        bind_keys = [f"key_{idx}" for idx, _ in enumerate(sorted(active_keys))]
        params: dict[str, Any] = {
            "storage_root_id": int(storage_root_id),
            "open_status": OPEN_STATUS,
            "resolved_status": RESOLVED_STATUS,
            "now": utcnow_naive(),
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

    def _membership_drift_alerts(
        self,
        *,
        root_id: int,
        identity_source_id: int,
        profile_rows: list[dict[str, Any]],
        base: Any,
        root_label: str,
    ) -> list[dict[str, Any]]:
        """AD group members vs granted accesses, from the latest snapshot (data sync).

        Expected members: requests executed on this root and level, neither revoked nor expired.
        Actual members: direct members of the group in the active snapshot. A group absent from the
        snapshot is not judged (nothing to compare with).
        """
        alerts: list[dict[str, Any]] = []
        for row in profile_rows:
            if str(row.get("status") or "").upper() != "SUCCEEDED":
                continue
            level = str(row.get("access_level") or "READ").upper()
            group_name = str(row.get("group_name") or "").strip()
            group = self._one(
                """
                SELECT dg.id
                FROM directory_groups dg
                WHERE dg.identity_source_id = :source_id
                  AND (
                    (:external_id <> '' AND LOWER(dg.external_id) = LOWER(:external_id))
                    OR LOWER(dg.name) = LOWER(:group_name)
                  )
                ORDER BY (LOWER(dg.external_id) = LOWER(:external_id)) DESC
                LIMIT 1
                """,
                {"source_id": identity_source_id, "external_id": str(row.get("group_external_id") or ""), "group_name": group_name},
            )
            if not group:
                continue
            actual = {
                str(m.get("username") or "").lower(): str(m.get("display_name") or m.get("username") or "")
                for m in self._all(
                    """
                    SELECT du.username, du.display_name
                    FROM directory_effective_memberships dem
                    JOIN directory_users du ON du.id = dem.directory_user_id
                    WHERE dem.directory_group_id = :group_id AND dem.depth = 0 AND du.username IS NOT NULL
                    """,
                    {"group_id": int(group["id"])},
                )
            }
            expected = {
                str(r.get("username") or "").lower(): str(r.get("display_name") or r.get("username") or "")
                for r in self._all(
                    """
                    SELECT
                      JSON_UNQUOTE(JSON_EXTRACT(ar.requested_principal_json, '$.username')) AS username,
                      JSON_UNQUOTE(JSON_EXTRACT(ar.requested_principal_json, '$.display_name')) AS display_name
                    FROM access_requests ar
                    JOIN access_request_items ari ON ari.access_request_id = ar.id
                    WHERE LOWER(ar.status) = 'executed'
                      AND ar.revoked_at IS NULL
                      AND ari.target_type = 'storage_root' AND ari.target_id = :root_id
                      AND UPPER(ari.permission) = :level
                      AND (ari.expires_at IS NULL OR ari.expires_at > UTC_TIMESTAMP())
                      AND LOWER(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(ar.requested_principal_json, '$.type')), 'user')) = 'user'
                    """,
                    {"root_id": root_id, "level": level},
                )
                if r.get("username") and str(r.get("username")) != "null"
            }
            profile_id = int(row.get("id") or 0)
            missing = sorted(set(expected) - set(actual))
            extra = sorted(set(actual) - set(expected))
            if missing:
                alerts.append({
                    **base("ad_member_missing"),
                    "alert_key": f"storage_root:{root_id}:ad_member_missing:{profile_id}",
                    "severity": "high",
                    "title": f"{level} access granted but missing from the AD group",
                    "message": f"{group_name}: " + ", ".join(expected[u] for u in missing[:10]) + (f" (+{len(missing) - 10})" if len(missing) > 10 else ""),
                    "source_type": "membership_drift",
                    "source_id": str(profile_id),
                    "metadata_json": {"storage_root_name": root_label, "group_name": group_name, "access_level": level, "usernames": missing},
                })
            if extra:
                alerts.append({
                    **base("ad_member_not_granted"),
                    "alert_key": f"storage_root:{root_id}:ad_member_not_granted:{profile_id}",
                    "severity": "warning",
                    "title": f"AD group member without a granted {level} access",
                    "message": f"{group_name}: " + ", ".join(actual[u] for u in extra[:10]) + (f" (+{len(extra) - 10})" if len(extra) > 10 else ""),
                    "source_type": "membership_drift",
                    "source_id": str(profile_id),
                    "metadata_json": {"storage_root_name": root_label, "group_name": group_name, "access_level": level, "usernames": extra},
                })
        return alerts

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
              srap.access_level_code AS access_level,
              srap.group_name,
              srap.group_external_id,
              UPPER(srap.status) AS status,
              srap.error_message
            FROM storage_root_access_profiles srap
            WHERE srap.storage_root_id = :storage_root_id
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
        for row in profile_rows:
            profile_status = str(row.get("status") or "").strip().upper()
            access_level = str(row.get("access_level") or "READ").strip().upper()
            group_name = str(row.get("group_name") or "").strip() or None
            normalized_group = normalize_principal(group_name)
            if normalized_group:
                expected_groups.add(normalized_group)
            if profile_status != "SUCCEEDED":
                is_pending = profile_status == "PENDING"
                alert_type = f"ad_group_{access_level.lower()}_{'pending' if is_pending else 'failed'}"
                profile_id = int(row.get("id") or 0)
                alert = {
                    **base(alert_type),
                    "alert_key": f"storage_root:{root_id}:{alert_type}:{profile_id}",
                    "severity": "warning" if is_pending else "high",
                    "title": f"{access_level} group {'being created' if is_pending else 'creation failed'}",
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

        if identity_source_id:
            alerts.extend(
                self._membership_drift_alerts(
                    root_id=root_id,
                    identity_source_id=int(identity_source_id),
                    profile_rows=profile_rows,
                    base=base,
                    root_label=root_label,
                )
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
