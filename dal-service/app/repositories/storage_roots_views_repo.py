from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.repositories.sql_view_repo import SQLViewRepo
from app.services.activity_bridge import list_activity_by_target
from app.services.naming_policy import resolve_effective_policy, resolve_group_name_from_effective_policy
from app.services.storage_root_binding_materialization_service import (
    CANONICAL_PERMISSIONS,
    compute_effective_root_bindings,
)


class StorageRootsViewsRepo(SQLViewRepo):
    """
    Read-model repository for Storage Roots (v4 minimal)

    Backed by SQL sources:
      - storage_roots/storage_endpoints/zones (list + detail)
    """

    def __init__(self, db: Session):
        super().__init__(db)

    @staticmethod
    def _extract_sam_account_name(naming_payload: dict[str, Any] | None) -> str | None:
        value = str((naming_payload or {}).get("samAccountName") or "").strip()
        return value or None

    def _load_tags_map(self, storage_root_ids: list[int]) -> dict[int, list[dict]]:
        normalized_ids = sorted({int(v) for v in (storage_root_ids or []) if int(v) > 0})
        if not normalized_ids:
            return {}

        bind_keys = [f"id_{idx}" for idx, _ in enumerate(normalized_ids)]
        params = {key: value for key, value in zip(bind_keys, normalized_ids)}
        in_clause = ", ".join(f":{key}" for key in bind_keys)

        rows = self._all(
            f"""
            SELECT
              srt.storage_root_id,
              t.id AS tag_id,
              t.name AS tag_name,
              t.color AS tag_color
            FROM storage_root_tags srt
            JOIN tags t ON t.id = srt.tag_id
            WHERE srt.storage_root_id IN ({in_clause})
              AND srt.deleted_at IS NULL
              AND t.deleted_at IS NULL
            ORDER BY srt.storage_root_id, t.name, t.id
            """,
            params,
        )

        out: dict[int, list[dict]] = {rid: [] for rid in normalized_ids}
        for row in rows:
            storage_root_id = int(row.get("storage_root_id") or 0)
            if storage_root_id <= 0:
                continue
            tag_id = int(row.get("tag_id") or 0)
            if tag_id <= 0:
                continue
            name = str(row.get("tag_name") or "").strip()
            color = str(row.get("tag_color") or "").strip() or None
            out.setdefault(storage_root_id, []).append(
                {
                    "id": tag_id,
                    "tag_id": tag_id,
                    "name": name or None,
                    "label": name or None,
                    "color": color,
                    "color_rgb": color,
                }
            )
        return out

    @staticmethod
    def _normalize_effective_availability(status: Any) -> str:
        key = str(status or "").strip().lower()
        if key == "success":
            return "reachable"
        if key == "running":
            return "checking"
        if key == "failed":
            return "unreachable"
        return "unknown"

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except Exception:
            return None

    @classmethod
    def _format_size_label(cls, value: Any) -> str | None:
        size_bytes = cls._coerce_int(value)
        if size_bytes is None or size_bytes < 0:
            return None
        units = ("B", "KB", "MB", "GB", "TB", "PB")
        scaled = float(size_bytes)
        unit = units[0]
        for candidate in units[1:]:
            if scaled < 1024.0:
                break
            scaled /= 1024.0
            unit = candidate
        if unit == "B":
            return f"{int(scaled)} {unit}"
        precision = 0 if scaled >= 100 else 1 if scaled >= 10 else 2
        text_value = f"{scaled:.{precision}f}".rstrip("0").rstrip(".")
        return f"{text_value} {unit}"

    def _content_metrics_from_payload(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        raw = dict(payload or {})
        size_bytes = (
            self._coerce_int(raw.get("content_size_bytes"))
            or self._coerce_int(raw.get("estimated_size_bytes"))
            or self._coerce_int(raw.get("size_bytes"))
            or self._coerce_int(raw.get("folder_size_bytes"))
        )
        scanned_at = (
            str(raw.get("content_updated_at") or "").strip()
            or str(raw.get("last_content_scan_at") or "").strip()
            or str(raw.get("size_scanned_at") or "").strip()
            or str(raw.get("discovered_at") or "").strip()
            or None
        )
        label = (
            str(raw.get("content_size_label") or "").strip()
            or str(raw.get("estimated_size_label") or "").strip()
            or self._format_size_label(size_bytes)
        )
        return {
            "content_size_bytes": size_bytes,
            "estimated_size_bytes": size_bytes,
            "content_size_label": label or None,
            "estimated_size_label": label or None,
            "content_updated_at": scanned_at,
            "last_content_scan_at": scanned_at,
        }

    def _augment_root_payload(self, row: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(row or {})
        acl_payload = self._json_dict(payload.get("discovered_permissions_json"))
        payload.update(self._content_metrics_from_payload(acl_payload))
        payload["effective_availability"] = self._compute_effective_availability(payload)
        return payload

    def _compute_effective_availability(self, row: dict[str, Any] | None) -> str:
        payload = dict(row or {})
        backend_effective = str(payload.get("effective_availability") or "").strip().lower()
        if backend_effective in {
            "reachable",
            "checking",
            "unreachable",
            "unknown",
            "blocked_by_endpoint",
            "needs_revalidation",
            "root_unreachable",
            "needs_root_probe",
            "not_provisioned",
        }:
            return backend_effective
        if bool(payload.get("needs_revalidation")):
            return "needs_revalidation"
        endpoint_status = str(payload.get("storage_endpoint_last_probe_status") or "").strip().lower()
        root_status = str(payload.get("last_probe_status") or "").strip().lower()
        provisioning_status = str(
            payload.get("provisioning_status")
            or payload.get("effective_provisioning_status")
            or ""
        ).strip().lower()
        if root_status == "success":
            return "reachable"
        if root_status == "running":
            return "checking"
        if provisioning_status and provisioning_status not in {"ready", "success", "succeeded", "active"}:
            return "not_provisioned"
        if endpoint_status == "failed":
            return "blocked_by_endpoint"
        if endpoint_status == "running":
            return "checking"
        if endpoint_status == "success":
            if root_status == "failed":
                return "root_unreachable"
            if root_status == "success":
                return "reachable"
            if root_status == "running":
                return "checking"
            return "needs_root_probe"
        return self._normalize_effective_availability(
            endpoint_status or root_status
        )

    def _load_revalidation_map(self, storage_root_ids: list[int]) -> dict[int, dict[str, Any]]:
        normalized_ids = sorted({int(v) for v in (storage_root_ids or []) if int(v) > 0})
        if not normalized_ids:
            return {}

        bind_keys = [f"root_reval_id_{idx}" for idx, _ in enumerate(normalized_ids)]
        params = {key: value for key, value in zip(bind_keys, normalized_ids)}
        in_clause = ", ".join(f":{key}" for key in bind_keys)

        rows = self._all(
            f"""
            SELECT
              id AS storage_root_id,
              needs_revalidation,
              revalidation_reason
            FROM storage_roots
            WHERE id IN ({in_clause})
            """,
            params,
        )
        return {
            int(row.get("storage_root_id") or 0): {
                "needs_revalidation": bool(row.get("needs_revalidation")),
                "revalidation_reason": row.get("revalidation_reason"),
            }
            for row in rows
            if int(row.get("storage_root_id") or 0) > 0
        }

    def _load_pending_validation_counts(self, storage_root_ids: list[int]) -> dict[int, int]:
        normalized_ids = sorted({int(v) for v in (storage_root_ids or []) if int(v) > 0})
        if not normalized_ids:
            return {}

        bind_keys = [f"root_id_{idx}" for idx, _ in enumerate(normalized_ids)]
        params = {key: value for key, value in zip(bind_keys, normalized_ids)}
        in_clause = ", ".join(f":{key}" for key in bind_keys)

        rows = self._all(
            f"""
            SELECT
              storage_root_id,
              COUNT(*) AS pending_validation_count
            FROM v_access_requests
            WHERE LOWER(COALESCE(status, '')) = 'pending'
              AND storage_root_id IN ({in_clause})
            GROUP BY storage_root_id
            """,
            params,
        )

        return {
            int(row.get("storage_root_id") or 0): int(row.get("pending_validation_count") or 0)
            for row in rows
            if int(row.get("storage_root_id") or 0) > 0
        }

    @staticmethod
    def _read_backend_pending_validation_count(row: dict[str, Any] | None) -> int | None:
        payload = dict(row or {})
        raw = payload.get("pending_validation_count")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return max(0, value)

    def _load_open_alerts_map(self, storage_root_ids: list[int]) -> dict[int, dict[str, Any]]:
        normalized_ids = sorted({int(v) for v in (storage_root_ids or []) if int(v) > 0})
        if not normalized_ids:
            return {}

        bind_keys = [f"root_id_{idx}" for idx, _ in enumerate(normalized_ids)]
        params = {key: value for key, value in zip(bind_keys, normalized_ids)}
        in_clause = ", ".join(f":{key}" for key in bind_keys)

        rows = self._all(
            f"""
            SELECT
              storage_root_id,
              COUNT(*) AS open_alerts_count,
              SUM(CASE WHEN LOWER(severity) IN ('critical', 'high') THEN 1 ELSE 0 END) AS open_alerts_error_count,
              GROUP_CONCAT(DISTINCT alert_type ORDER BY alert_type SEPARATOR ',') AS open_alert_types
            FROM governance_alerts
            WHERE status = 'open'
              AND storage_root_id IN ({in_clause})
            GROUP BY storage_root_id
            """,
            params,
        )
        return {
            int(row.get("storage_root_id") or 0): {
                "open_alerts_count": int(row.get("open_alerts_count") or 0),
                "open_alerts_error_count": int(row.get("open_alerts_error_count") or 0),
                "open_alert_types": str(row.get("open_alert_types") or ""),
            }
            for row in rows
            if int(row.get("storage_root_id") or 0) > 0
        }

    def _load_open_alerts_for_root(self, storage_root_id: int) -> list[dict[str, Any]]:
        return self._all_dicts(
            """
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
              metadata_json
            FROM governance_alerts
            WHERE status = 'open'
              AND storage_root_id = :storage_root_id
            ORDER BY
              CASE LOWER(severity)
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'warning' THEN 3
                ELSE 4
              END,
              last_seen_at DESC,
              id DESC
            """,
            {"storage_root_id": int(storage_root_id)},
        )

    def _load_discovered_tree_map(self, storage_root_ids: list[int]) -> dict[int, Any]:
        normalized_ids = sorted({int(v) for v in (storage_root_ids or []) if int(v) > 0})
        if not normalized_ids:
            return {}

        bind_keys = [f"root_id_{idx}" for idx, _ in enumerate(normalized_ids)]
        params = {key: value for key, value in zip(bind_keys, normalized_ids)}
        in_clause = ", ".join(f":{key}" for key in bind_keys)

        rows = self._all(
            f"""
            SELECT id AS storage_root_id, discovered_tree_json
            FROM storage_roots
            WHERE id IN ({in_clause})
            """,
            params,
        )

        return {
            int(row.get("storage_root_id") or 0): row.get("discovered_tree_json")
            for row in rows
            if int(row.get("storage_root_id") or 0) > 0 and row.get("discovered_tree_json") is not None
        }

    @staticmethod
    def _load_recent_activity_for_root(storage_root_id: int, *, limit: int = 5) -> list[dict[str, Any]]:
        if int(storage_root_id) <= 0:
            return []
        rows = list_activity_by_target(
            target_type="storage_root",
            target_id=int(storage_root_id),
            limit=int(limit),
        )
        return rows if isinstance(rows, list) else []

    # ============================================================
    # CONTEXT (LIST)
    # ============================================================

    def list_context(
        self,
        *,
        zone_id: int | None = None,
        storage_endpoint_id: int | None = None,
    ) -> list[dict]:
        """Global contextual list (tree / browsing).

        Backed by base tables (v4 minimal).
        """

        where: list[str] = []
        params: dict = {}

        if zone_id is not None:
            where.append("zone_id = :zone_id")
            params["zone_id"] = int(zone_id)
        if storage_endpoint_id is not None:
            where.append("storage_endpoint_id = :storage_endpoint_id")
            params["storage_endpoint_id"] = int(storage_endpoint_id)

        sql = """
            SELECT
              storage_root_id,
              storage_root_name,
              root_path,
              normalized_root_path,
              parent_storage_root_id,
              parent_storage_root_name,
              parent_root_path,
              inherit_owners,
              inherit_tags,
              inherit_access_profiles,
              storage_root_status AS status,
              created_at,
              last_probe_status,
              last_probe_at,
              last_probe_message,
              last_discovery_at,
              last_scan_at,
              discovered_permissions_json,
              discovered_permissions,
              storage_endpoint_id,
              storage_endpoint_name,
              storage_endpoint_type,
              storage_endpoint_host,
              storage_endpoint_port,
              storage_endpoint_last_probe_status,
              storage_endpoint_last_probe_at,
              storage_endpoint_last_probe_message,
              zone_id,
              zone_name
            FROM v_storage_roots_context
        """
        if where:
            sql += "\nWHERE " + " AND ".join(where)

        sql += "\nORDER BY zone_name, storage_root_name"

        rows = self._all(sql, params)
        storage_root_ids = [int(r.get("storage_root_id") or 0) for r in rows if int(r.get("storage_root_id") or 0) > 0]
        tags_by_root_id = self._load_tags_map(storage_root_ids)
        pending_counts_by_root_id = self._load_pending_validation_counts(storage_root_ids)
        alerts_by_root_id = self._load_open_alerts_map(storage_root_ids)
        discovered_tree_by_root_id = self._load_discovered_tree_map(storage_root_ids)
        revalidation_by_root_id = self._load_revalidation_map(storage_root_ids)

        out: list[dict] = []
        for row in rows:
            payload = self._augment_root_payload(row)
            storage_root_id = int(payload.get("storage_root_id") or 0)
            payload["tags"] = tags_by_root_id.get(storage_root_id, [])
            backend_pending = self._read_backend_pending_validation_count(payload)
            payload["pending_validation_count"] = (
                backend_pending
                if backend_pending is not None
                else int(pending_counts_by_root_id.get(storage_root_id, 0))
            )
            payload.update(revalidation_by_root_id.get(storage_root_id, {}))
            alert_summary = alerts_by_root_id.get(storage_root_id, {})
            payload["open_alerts_count"] = int(alert_summary.get("open_alerts_count") or 0)
            payload["open_alerts_error_count"] = int(alert_summary.get("open_alerts_error_count") or 0)
            payload["open_alert_types"] = str(alert_summary.get("open_alert_types") or "")
            payload["discovered_tree_json"] = discovered_tree_by_root_id.get(storage_root_id)
            out.append(payload)
        return out

    # ============================================================
    # OVERVIEW (DETAIL)
    # ============================================================

    def get_overview(
        self,
        storage_root_id: int,
    ) -> dict | None:
        """Single storage root overview (v4 minimal).

        Backed by base tables (v4 minimal).
        """

        row = self._one_dict(
            """
            SELECT
              c.storage_root_id,
              c.storage_root_name,
              c.root_path,
              c.normalized_root_path,
              c.parent_storage_root_id,
              c.parent_storage_root_name,
              c.parent_root_path,
              c.inherit_owners,
              c.inherit_tags,
              c.inherit_access_profiles,
              c.storage_root_status AS status,
              c.created_at,
              c.last_probe_status,
              c.last_probe_at,
              c.last_probe_message,
              c.last_discovery_at,
              c.last_scan_at,
              c.discovered_permissions_json,
              c.discovered_permissions,
              c.storage_endpoint_id,
              se.identity_source_id AS storage_endpoint_identity_source_id,
              c.storage_endpoint_name,
              c.storage_endpoint_type,
              c.storage_endpoint_host,
              c.storage_endpoint_port,
              c.storage_endpoint_last_probe_status,
              c.storage_endpoint_last_probe_at,
              c.storage_endpoint_last_probe_message,
              c.zone_id,
              c.zone_name
            FROM v_storage_roots_context c
            LEFT JOIN storage_endpoints se ON se.id = c.storage_endpoint_id
            WHERE c.storage_root_id = :id
            """,
            {"id": storage_root_id},
        )
        if row is None:
            return None

        row = self._augment_root_payload(row)

        tags_by_root_id = self._load_tags_map([int(storage_root_id)])
        row["tags"] = tags_by_root_id.get(int(storage_root_id), [])
        backend_pending = self._read_backend_pending_validation_count(row)
        row["pending_validation_count"] = (
            backend_pending
            if backend_pending is not None
            else int(self._load_pending_validation_counts([int(storage_root_id)]).get(int(storage_root_id), 0))
        )
        row.update(self._load_revalidation_map([int(storage_root_id)]).get(int(storage_root_id), {}))
        alerts = self._load_open_alerts_for_root(int(storage_root_id))
        row["governance_alerts"] = alerts
        row["open_alerts_count"] = int(len(alerts))
        row["open_alerts_error_count"] = sum(
            1 for alert in alerts if str(alert.get("severity") or "").strip().lower() in {"critical", "high"}
        )
        row["discovered_tree_json"] = self._load_discovered_tree_map([int(storage_root_id)]).get(int(storage_root_id))
        row["recent_activity"] = self._load_recent_activity_for_root(int(storage_root_id), limit=5)
        return row


    # ============================================================
    # APPLIED ACCESS (READ-ONLY)
    # ============================================================

    def list_applied_access(self) -> list[dict]:
        """
        Global applied access from storage_root_roles.
        """

        return (
            self.db.execute(
                text(
                    """
                    SELECT
                      srr.root_id AS storage_root_id,
                      srr.identity_id,
                      LOWER(srr.role) AS role,
                      srr.assigned_at AS granted_at,
                      NULL AS granted_by_job_id,
                      NULL AS revoked_at,
                      NULL AS revoked_by_job_id
                    FROM storage_root_roles srr
                    WHERE LOWER(srr.role) = 'guardian'
                    """
                )
            )
            .mappings()
            .all()
        )

    def list_owners(self, storage_root_id: int) -> list[dict]:
        # Read directly from base tables instead of depending on SQL view shape.
        # This avoids stale-view drift in long-lived environments where views may
        # not have been rebuilt yet, while keeping the exact same output contract.
        rows = self._all_dicts(
            """
            SELECT
              srr.root_id AS storage_root_id,
              srr.identity_id AS identity_id,
              LOWER(srr.role) AS role,
              i.display_name AS display_name,
              i.username AS username,
              i.email AS email,
              i.type AS identity_type
            FROM storage_root_roles srr
            LEFT JOIN identities i ON i.id = srr.identity_id
            WHERE srr.root_id = :storage_root_id
              AND LOWER(srr.role) = 'guardian'
            ORDER BY COALESCE(i.display_name, i.username, i.email, CAST(srr.identity_id AS CHAR))
            """,
            {"storage_root_id": int(storage_root_id)},
        )

        deduped: list[dict[str, Any]] = []
        seen: set[tuple[int, int, str]] = set()
        for row in rows:
            root_id = int(row.get("storage_root_id") or 0)
            identity_id = int(row.get("identity_id") or 0)
            role = str(row.get("role") or "").strip().lower()
            if root_id <= 0 or identity_id <= 0 or role != "guardian":
                continue

            key = (root_id, identity_id, role)
            if key in seen:
                continue
            seen.add(key)

            deduped.append(
                {
                    "storage_root_id": root_id,
                    "identity_id": identity_id,
                    "role": role,
                    "display_name": row.get("display_name"),
                    "username": row.get("username"),
                    "email": row.get("email"),
                    "identity_type": row.get("identity_type"),
                }
            )

        return deduped

    # ============================================================
    # EFFECTIVE ACCESS (READ/WRITE users)
    # ============================================================

    @staticmethod
    def _json_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _acl_principal_candidates(value: Any) -> list[str]:
        raw = str(value or "").strip()
        if not raw:
            return []

        candidates = [raw]
        normalized = raw.replace("/", "\\")
        if "\\" in normalized:
            candidates.append(normalized.split("\\")[-1].strip())
        if "@" in raw:
            candidates.append(raw.split("@", 1)[0].strip())
        if raw.upper().startswith("CN="):
            cn = raw.split(",", 1)[0].split("=", 1)[-1].strip()
            candidates.append(cn)

        out: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            key = item.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item.strip())
        return out

    @staticmethod
    def _acl_principal_namespace(value: Any) -> str:
        raw = str(value or "").strip().replace("/", "\\")
        if "\\" not in raw:
            return ""
        return raw.split("\\", 1)[0].strip().upper()

    @classmethod
    def _is_well_known_acl_principal(cls, value: Any) -> bool:
        raw = str(value or "").strip().upper()
        namespace = cls._acl_principal_namespace(raw)
        return namespace in {"BUILTIN", "NT AUTHORITY"} or raw in {"EVERYONE", "AUTHENTICATED USERS"}

    def _root_acl_context(self, storage_root_id: int) -> tuple[list[dict[str, Any]], int | None, str | None]:
        row = self._one_dict(
            """
            SELECT
              sr.discovered_permissions_json,
              se.identity_source_id
            FROM storage_roots sr
            LEFT JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            WHERE sr.id = :storage_root_id
            LIMIT 1
            """,
            {"storage_root_id": int(storage_root_id)},
        )
        if not row:
            return [], None, None

        payload = self._json_dict(row.get("discovered_permissions_json"))
        raw_permissions = payload.get("permissions")
        permissions = [dict(item) for item in raw_permissions if isinstance(item, dict)] if isinstance(raw_permissions, list) else []
        identity_source_id = int(row.get("identity_source_id") or 0) or None
        discovered_at = str(payload.get("discovered_at") or "").strip() or None
        return permissions, identity_source_id, discovered_at

    def _resolve_acl_members(
        self,
        *,
        principal: str,
        identity_source_id: int | None,
    ) -> tuple[list[dict[str, Any]], bool]:
        if self._is_well_known_acl_principal(principal):
            return [], False

        group_found = False
        members: list[dict[str, Any]] = []
        for candidate in self._acl_principal_candidates(principal):
            if not group_found and self._ad_group_exists_for_identity_source(
                group_ref=candidate,
                identity_source_id=identity_source_id,
            ):
                group_found = True

            if not members:
                members = self._list_group_members_from_effective_memberships(
                    group_ref=candidate,
                    identity_source_id=identity_source_id,
                )
            if not members:
                members = self._list_group_members_from_directory_group_members(
                    group_ref=candidate,
                    identity_source_id=identity_source_id,
                )
            if not members:
                members = self._list_group_members_from_active_snapshot_payload(
                    group_ref=candidate,
                    identity_source_id=identity_source_id,
                )
            if members:
                group_found = True
                break

        return self._dedupe_group_member_rows(members), group_found

    def _build_acl_effective_access_rows(self, storage_root_id: int) -> list[dict[str, Any]]:
        permissions, identity_source_id, discovered_at = self._root_acl_context(storage_root_id)
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        for permission in permissions:
            principal = str(permission.get("principal") or permission.get("name") or "").strip()
            if not principal:
                continue
            level = str(permission.get("access_level") or "read").strip().lower()
            if level not in {"read", "write"}:
                level = "write" if level in {"full", "modify", "rw"} else "read"
            raw_rights = str(permission.get("raw") or permission.get("rights") or "").strip()
            key = (principal.lower(), level, raw_rights.lower())
            if key in seen:
                continue
            seen.add(key)

            members, group_found = self._resolve_acl_members(
                principal=principal,
                identity_source_id=identity_source_id,
            )
            candidates = self._acl_principal_candidates(principal)
            display_name = candidates[-1] if candidates else principal
            principal_type = "well_known" if self._is_well_known_acl_principal(principal) else (
                "ad_group" if group_found else "acl_principal"
            )
            member_rows = [
                {
                    **member,
                    "row_id": f"acl-member:{principal.lower()}:{level}:{idx}:{member.get('identity_id') or member.get('upn') or member.get('username')}",
                    "access_level": level,
                    "source": "acl",
                    "access_source": "acl",
                    "principal": principal,
                    "acl_parent_principal": principal,
                    "granted_at": discovered_at,
                    "granted_by": principal,
                    "granted_by_display_name": display_name,
                    "raw_acl": raw_rights,
                }
                for idx, member in enumerate(members)
            ]

            out.append(
                {
                    "row_id": f"acl:{principal.lower()}:{level}:{len(out)}",
                    "identity_id": None,
                    "display_name": display_name,
                    "username": principal,
                    "email": None,
                    "upn": principal,
                    "identity_source_id": identity_source_id,
                    "directory_snapshot_id": self._active_snapshot_id_for_source(identity_source_id=identity_source_id),
                    "access_level": level,
                    "source": "acl",
                    "access_source": "acl",
                    "created_at": discovered_at,
                    "assigned_at": discovered_at,
                    "granted_at": discovered_at,
                    "expires_at": None,
                    "granted_by": "filesystem_acl",
                    "granted_by_display_name": "Filesystem ACL",
                    "source_entries": 1,
                    "principal": principal,
                    "principal_type": principal_type,
                    "is_acl_group": bool(group_found),
                    "members_count": len(member_rows),
                    "members": member_rows,
                    "raw_acl": raw_rights,
                }
            )
        return out

    def _acl_principal_index(self, storage_root_id: int) -> dict[str, dict[str, Any]]:
        permissions, _, discovered_at = self._root_acl_context(storage_root_id)
        out: dict[str, dict[str, Any]] = {}
        for permission in permissions:
            principal = str(permission.get("principal") or "").strip()
            if not principal:
                continue
            keys = self._acl_principal_candidates(principal)
            for key in keys:
                out[key.lower()] = {
                    "principal": principal,
                    "access_level": str(permission.get("access_level") or "").strip().lower() or None,
                    "raw": permission.get("raw"),
                    "discovered_at": discovered_at,
                }
        return out

    @staticmethod
    def _acl_alignment_for_group(group_name: str | None, acl_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
        raw = str(group_name or "").strip()
        if not raw or not acl_index:
            return {
                "acl_alignment": "unknown",
                "acl_principal": None,
                "acl_access_level": None,
                "acl_raw": None,
            }
        for candidate in StorageRootsViewsRepo._acl_principal_candidates(raw):
            match = acl_index.get(candidate.lower())
            if match:
                return {
                    "acl_alignment": "present",
                    "acl_principal": match.get("principal"),
                    "acl_access_level": match.get("access_level"),
                    "acl_raw": match.get("raw"),
                    "acl_discovered_at": match.get("discovered_at"),
                }
        return {
            "acl_alignment": "missing",
            "acl_principal": None,
            "acl_access_level": None,
            "acl_raw": None,
        }

    def get_acl_freshness(self, storage_root_id: int) -> dict[str, Any]:
        row = self._one_dict(
            """
            SELECT
              sr.discovered_permissions_json,
              se.identity_source_id,
              ds.id AS active_snapshot_id,
              COALESCE(ds.activated_at, ds.completed_at, ds.finished_at, ds.updated_at) AS active_snapshot_at
            FROM storage_roots sr
            LEFT JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            LEFT JOIN directory_snapshots ds
              ON ds.id = (
                SELECT ds2.id
                FROM directory_snapshots ds2
                WHERE ds2.identity_source_id = se.identity_source_id
                  AND UPPER(COALESCE(ds2.status, '')) = 'ACTIVE'
                ORDER BY ds2.version DESC, ds2.id DESC
                LIMIT 1
              )
            WHERE sr.id = :storage_root_id
            LIMIT 1
            """,
            {"storage_root_id": int(storage_root_id)},
        )
        if not row:
            return {
                "state": "unknown",
                "reason": "storage_root_not_found",
                "permissions_count": 0,
            }

        payload = self._json_dict(row.get("discovered_permissions_json"))
        permissions = payload.get("permissions") if isinstance(payload.get("permissions"), list) else []
        scanned_at = str(payload.get("discovered_at") or "").strip() or None
        snapshot_at = row.get("active_snapshot_at")
        snapshot_id = int(row.get("active_snapshot_id") or 0) or None

        if not scanned_at:
            state = "not_scanned"
            reason = "acl_not_scanned"
        elif snapshot_at and str(snapshot_at) > str(scanned_at).replace("T", " ").replace("+00:00", ""):
            state = "stale"
            reason = "identity_snapshot_newer_than_acl_scan"
        else:
            state = "fresh"
            reason = "acl_scan_current"

        return {
            "state": state,
            "reason": reason,
            "scanned_at": scanned_at,
            "source": payload.get("source"),
            "probe_job_id": payload.get("probe_job_id"),
            "permissions_count": int(payload.get("permissions_count") or len(permissions) or 0),
            "active_snapshot_id": snapshot_id,
            "active_snapshot_at": snapshot_at,
            "identity_source_id": int(row.get("identity_source_id") or 0) or None,
        }

    def get_effective_access_details(self, storage_root_id: int) -> dict:
        users = self._all_dicts(
            """
            SELECT
              actor_id AS identity_id,
              MAX(actor_display_name) AS display_name,
              COALESCE(MAX(actor_external_id), MAX(actor_display_name)) AS username,
              CAST(NULL AS CHAR(255)) AS email,
              MAX(actor_external_id) AS upn,
              MAX(identity_source_id) AS identity_source_id,
              MAX(directory_snapshot_id) AS directory_snapshot_id,
              CASE
                WHEN SUM(CASE WHEN LOWER(access_level) = 'write' THEN 1 ELSE 0 END) > 0 THEN 'write'
                ELSE 'read'
              END AS access_level,
              CASE
                WHEN SUM(CASE WHEN LOWER(COALESCE(source, '')) = 'request' THEN 1 ELSE 0 END) > 0 THEN 'request'
                WHEN SUM(CASE WHEN LOWER(COALESCE(source, '')) = 'inherited' THEN 1 ELSE 0 END) > 0 THEN 'inherited'
                WHEN SUM(CASE WHEN LOWER(COALESCE(source, '')) = 'manual' THEN 1 ELSE 0 END) > 0 THEN 'manual'
                ELSE 'unknown'
              END AS source,
              MAX(granted_at) AS granted_at,
              MAX(expires_at) AS expires_at,
              COUNT(*) AS source_entries
            FROM v_storage_root_effective_access
            WHERE storage_root_id = :storage_root_id
              AND actor_id IS NOT NULL
            GROUP BY actor_id
            ORDER BY LOWER(MAX(actor_display_name)), actor_id
            """,
            {"storage_root_id": int(storage_root_id)},
        )
        acl_rows = self._build_acl_effective_access_rows(int(storage_root_id))
        if acl_rows:
            users = [*users, *acl_rows]

        read_users = sum(1 for u in users if str(u.get("access_level") or "").lower() == "read")
        write_users = sum(1 for u in users if str(u.get("access_level") or "").lower() == "write")

        return {
            "read_users": read_users,
            "write_users": write_users,
            "total_users": len(users),
            "users": users,
        }

    def get_effective_provisioning_policy(self, storage_root_id: int) -> dict | None:
        return self._one_dict(
            """
            SELECT *
            FROM v_storage_root_provisioning_effective
            WHERE storage_root_id = :storage_root_id
            LIMIT 1
            """,
            {"storage_root_id": int(storage_root_id)},
        )

    def serialize_access_profiles(self, *, storage_root_id: int) -> dict:
        acl_index = self._acl_principal_index(int(storage_root_id))
        rows = self._all_dicts(
            """
            SELECT
              srap.id,
              srap.access_profile_id,
              srap.source,
              srap.group_name AS group_dn,
              srap.group_name AS group_name,
              srap.group_external_id,
              UPPER(COALESCE(NULLIF(srap.access_level_code, ''), NULLIF(ap.code, ''), NULLIF(ap.permission, ''), 'READ')) AS access_level_code,
              srap.status,
              srap.created_at,
              srap.updated_at,
              srap.error_message,
              ap.name AS profile_name,
              ap.code AS profile_code,
              ap.permission AS profile_permission,
              pj.correlation_id,
              pj.error_message AS job_error_message,
              pj.updated_at AS job_updated_at,
              COALESCE((
                SELECT COUNT(DISTINCT ib.identity_id)
                FROM directory_groups dg
                JOIN directory_effective_memberships dem
                  ON dem.directory_group_id = dg.id
                 AND dem.identity_source_id = dg.identity_source_id
                JOIN identity_bindings ib
                  ON ib.directory_user_id = dem.directory_user_id
                 AND ib.deleted_at IS NULL
                WHERE dg.deleted_at IS NULL
                  AND (
                    LOWER(dg.name) = LOWER(COALESCE(NULLIF(srap.group_name, ''), ''))
                    OR LOWER(COALESCE(dg.external_id, '')) = LOWER(COALESCE(NULLIF(srap.group_external_id, ''), ''))
                    OR LOWER(COALESCE(dg.external_id, '')) = LOWER(COALESCE(NULLIF(srap.group_name, ''), ''))
                    OR LOWER(COALESCE(dg.dn, '')) = LOWER(COALESCE(NULLIF(srap.group_name, ''), ''))
                  )
              ), 0) AS members_count
            FROM storage_root_access_profiles srap
            LEFT JOIN access_profiles ap ON ap.id = srap.access_profile_id
            LEFT JOIN provisioning_jobs pj
              ON pj.id = (
                SELECT p2.id
                FROM provisioning_jobs p2
                WHERE p2.storage_root_access_profile_id = srap.id
                ORDER BY p2.id DESC
                LIMIT 1
              )
            WHERE srap.storage_root_id = :storage_root_id
              AND srap.deleted_at IS NULL
            ORDER BY srap.id ASC
            """,
            {"storage_root_id": int(storage_root_id)},
        )

        items: list[dict[str, Any]] = []
        for row in rows:
            access_profile_id = int(row.get("access_profile_id") or 0)
            normalized_status = str(row.get("status") or "PENDING").strip().upper()
            if normalized_status == "FAILED":
                normalized_status = "ERROR"
            items.append(
                {
                    "id": access_profile_id or int(row.get("id") or 0),
                    "link_id": int(row.get("id") or 0),
                    "access_profile_id": access_profile_id or None,
                    "group_name": str(row.get("group_name") or "").strip() or None,
                    "group_dn": str(row.get("group_dn") or "").strip() or None,
                    "group_external_id": str(row.get("group_external_id") or "").strip() or None,
                    "code": row.get("profile_code"),
                    "source": str(row.get("source") or "LOCAL").upper(),
                    "name": row.get("profile_name"),
                    "permission": row.get("profile_permission"),
                    "access_level": row.get("access_level_code") or "READ",
                    "status": normalized_status,
                    "members_count": int(row.get("members_count") or 0),
                    "error_message": (str(row.get("error_message") or "").strip() or None)
                    or (str(row.get("job_error_message") or "").strip() or None),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("job_updated_at") or row.get("updated_at"),
                    "last_error_message": (str(row.get("error_message") or "").strip() or None)
                    or (str(row.get("job_error_message") or "").strip() or None),
                    "correlation_id": row.get("correlation_id"),
                }
            )

        items_by_level: dict[str, list[dict[str, Any]]] = {"READ": [], "WRITE": []}
        for item in items:
            level = str(item.get("access_level") or "READ").strip().upper()
            if level not in items_by_level:
                level = "READ"
            items_by_level[level].append(item)

        inherited_status = compute_effective_root_bindings(self.db, storage_root_id=int(storage_root_id))
        approval_readiness: dict[str, bool] = {}
        binding_status: dict[str, str] = {}

        for permission in CANONICAL_PERMISSIONS:
            rows = items_by_level.get(permission, [])
            inherited = inherited_status.get(permission)
            has_materialized = len(rows) > 0
            inherited_state = str((inherited.status if inherited else "missing") or "missing")

            if has_materialized and len(rows) > 1:
                status_value = "ambiguous"
            elif has_materialized:
                status_value = "materialized"
            elif inherited_state == "resolved":
                status_value = "inherited_candidate"
            elif inherited_state == "ambiguous":
                status_value = "ambiguous"
            else:
                status_value = "missing"

            approval_readiness[permission] = status_value == "materialized"
            binding_status[permission] = status_value

            if status_value == "inherited_candidate" and inherited and inherited.resolved is not None:
                candidate = inherited.resolved
                items.append(
                    {
                        "id": int(candidate.access_profile_id),
                        "link_id": None,
                        "access_profile_id": int(candidate.access_profile_id),
                        "group_name": None,
                        "group_dn": None,
                        "group_external_id": None,
                        "code": candidate.profile_code,
                        "source": "INHERITED",
                        "name": candidate.profile_name,
                        "permission": permission,
                        "access_level": permission,
                        "status": "PENDING_MATERIALIZATION",
                        "members_count": 0,
                        "error_message": None,
                        "created_at": None,
                        "updated_at": None,
                        "last_error_message": None,
                        "correlation_id": None,
                        "is_materialized_on_root": False,
                        "binding_status": "inherited_candidate",
                    }
                )

            if status_value == "missing":
                items.append(
                    {
                        "id": None,
                        "link_id": None,
                        "access_profile_id": None,
                        "group_name": None,
                        "group_dn": None,
                        "group_external_id": None,
                        "code": permission,
                        "source": "NONE",
                        "name": None,
                        "permission": permission,
                        "access_level": permission,
                        "status": "BINDING_MISSING",
                        "members_count": 0,
                        "error_message": None,
                        "created_at": None,
                        "updated_at": None,
                        "last_error_message": None,
                        "correlation_id": None,
                        "is_materialized_on_root": False,
                        "binding_status": "missing",
                    }
                )

            if status_value == "ambiguous":
                items.append(
                    {
                        "id": None,
                        "link_id": None,
                        "access_profile_id": None,
                        "group_name": None,
                        "group_dn": None,
                        "group_external_id": None,
                        "code": permission,
                        "source": "MIXED",
                        "name": None,
                        "permission": permission,
                        "access_level": permission,
                        "status": "AMBIGUOUS_BINDING",
                        "members_count": 0,
                        "error_message": None,
                        "created_at": None,
                        "updated_at": None,
                        "last_error_message": None,
                        "correlation_id": None,
                        "is_materialized_on_root": False,
                        "binding_status": "ambiguous",
                    }
                )

        for item in items:
            level = str(item.get("access_level") or "READ").strip().upper()
            if level not in {"READ", "WRITE"}:
                level = "READ"
            item.setdefault("is_materialized_on_root", bool(item.get("link_id")))
            item.setdefault("binding_status", binding_status.get(level, "missing"))
            item.setdefault("approval_ready", bool(item.get("is_materialized_on_root")))
            item.update(self._acl_alignment_for_group(str(item.get("group_name") or ""), acl_index))

        return {
            "storage_root_id": int(storage_root_id),
            "items": items,
            "attached_profiles": [row for row in items if bool(row.get("is_materialized_on_root"))],
            "binding_status": binding_status,
            "approval_ready": all(bool(approval_readiness.get(p, False)) for p in CANONICAL_PERMISSIONS),
        }

    def _active_snapshot_id_for_source(self, *, identity_source_id: int | None) -> int | None:
        if identity_source_id is None or int(identity_source_id) <= 0:
            return None

        row = self._one_dict(
            """
            SELECT ds.id
            FROM directory_snapshots ds
            WHERE ds.identity_source_id = :identity_source_id
              AND UPPER(COALESCE(ds.status, '')) = 'ACTIVE'
            ORDER BY ds.version DESC, ds.id DESC
            LIMIT 1
            """,
            {"identity_source_id": int(identity_source_id)},
        )
        out = int((row or {}).get("id") or 0)
        return out if out > 0 else None

    @staticmethod
    def _dedupe_group_member_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            identity_id = int(row.get("identity_id") or 0)
            email = str(row.get("email") or "").strip().lower()
            username = str(row.get("username") or "").strip().lower()
            upn = str(row.get("upn") or "").strip().lower()
            key = f"id:{identity_id}" if identity_id > 0 else f"mail:{email}|user:{username}|upn:{upn}"
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        return out

    def _ad_group_exists_for_identity_source(
        self,
        *,
        group_ref: str,
        identity_source_id: int | None,
    ) -> bool:
        normalized = str(group_ref or "").strip()
        if not normalized:
            return False

        row = self._one_dict(
            """
            SELECT 1 AS ok
            FROM directory_groups dg
            WHERE dg.deleted_at IS NULL
              AND (:identity_source_id IS NULL OR dg.identity_source_id = :identity_source_id)
              AND (
                LOWER(COALESCE(dg.name, '')) = LOWER(:group_ref)
                OR LOWER(COALESCE(dg.external_id, '')) = LOWER(:group_ref)
                OR LOWER(COALESCE(dg.dn, '')) = LOWER(:group_ref)
              )
            LIMIT 1
            """,
            {
                "group_ref": normalized,
                "identity_source_id": int(identity_source_id) if identity_source_id else None,
            },
        )
        return row is not None

    def _list_group_members_from_effective_memberships(
        self,
        *,
        group_ref: str,
        identity_source_id: int | None,
    ) -> list[dict[str, Any]]:
        rows = self._all_dicts(
            """
            SELECT DISTINCT
              i.id AS identity_id,
              i.display_name AS display_name,
              i.username AS username,
              i.email AS email,
              du.upn AS upn,
              dem.snapshot_id AS snapshot_id
            FROM directory_groups dg
            JOIN directory_effective_memberships dem
              ON dem.directory_group_id = dg.id
             AND dem.identity_source_id = dg.identity_source_id
            JOIN directory_users du
              ON du.id = dem.directory_user_id
            JOIN identity_bindings ib
              ON ib.directory_user_id = du.id
             AND ib.deleted_at IS NULL
            JOIN identities i
              ON i.id = ib.identity_id
            LEFT JOIN directory_snapshots ds
              ON ds.id = dem.snapshot_id
            WHERE dg.deleted_at IS NULL
              AND (
                LOWER(dg.name) = LOWER(:group_ref)
                OR LOWER(COALESCE(dg.external_id, '')) = LOWER(:group_ref)
                OR LOWER(COALESCE(dg.dn, '')) = LOWER(:group_ref)
              )
              AND (:identity_source_id IS NULL OR dg.identity_source_id = :identity_source_id)
              AND (dem.snapshot_id IS NULL OR UPPER(COALESCE(ds.status, '')) = 'ACTIVE')
            ORDER BY COALESCE(i.display_name, i.username, i.email, CAST(i.id AS CHAR)) ASC
            """,
            {
                "group_ref": str(group_ref or "").strip(),
                "identity_source_id": int(identity_source_id) if identity_source_id else None,
            },
        )

        return [
            {
                "identity_id": int(row.get("identity_id") or 0),
                "display_name": row.get("display_name"),
                "username": row.get("username"),
                "email": row.get("email"),
                "upn": row.get("upn"),
                "snapshot_id": int(row.get("snapshot_id") or 0) or None,
                "source": "inherited",
            }
            for row in rows
            if int(row.get("identity_id") or 0) > 0
        ]

    def _list_group_members_from_directory_group_members(
        self,
        *,
        group_ref: str,
        identity_source_id: int | None,
    ) -> list[dict[str, Any]]:
        rows = self._all_dicts(
            """
            SELECT DISTINCT
              i.id AS identity_id,
              i.display_name AS display_name,
              i.username AS username,
              i.email AS email,
              du.upn AS upn
            FROM directory_groups dg
            JOIN directory_group_members dgm
              ON dgm.group_id = dg.id
             AND dgm.deleted_at IS NULL
            JOIN directory_users du
              ON du.id = dgm.directory_user_id
            JOIN identity_bindings ib
              ON ib.directory_user_id = du.id
             AND ib.deleted_at IS NULL
            JOIN identities i
              ON i.id = ib.identity_id
            WHERE dg.deleted_at IS NULL
              AND (
                LOWER(dg.name) = LOWER(:group_ref)
                OR LOWER(COALESCE(dg.external_id, '')) = LOWER(:group_ref)
                OR LOWER(COALESCE(dg.dn, '')) = LOWER(:group_ref)
              )
              AND (:identity_source_id IS NULL OR dg.identity_source_id = :identity_source_id)
            ORDER BY COALESCE(i.display_name, i.username, i.email, CAST(i.id AS CHAR)) ASC
            """,
            {
                "group_ref": str(group_ref or "").strip(),
                "identity_source_id": int(identity_source_id) if identity_source_id else None,
            },
        )

        return [
            {
                "identity_id": int(row.get("identity_id") or 0),
                "display_name": row.get("display_name"),
                "username": row.get("username"),
                "email": row.get("email"),
                "upn": row.get("upn"),
                "snapshot_id": None,
                "source": "inherited",
            }
            for row in rows
            if int(row.get("identity_id") or 0) > 0
        ]

    def _list_group_members_from_active_snapshot_payload(
        self,
        *,
        group_ref: str,
        identity_source_id: int | None,
    ) -> list[dict[str, Any]]:
        rows = self._all_dicts(
            """
            SELECT DISTINCT
              COALESCE(ib.identity_id, 0) AS identity_id,
              COALESCE(i.display_name, su.display_name, su.username, su.upn, su.email, su.external_id) AS display_name,
              COALESCE(i.username, su.username) AS username,
              COALESCE(i.email, su.email) AS email,
              su.upn AS upn,
              ds.id AS snapshot_id
            FROM directory_snapshots ds
            JOIN directory_snapshot_groups sg
              ON sg.snapshot_id = ds.id
            JOIN directory_snapshot_memberships sm
              ON sm.snapshot_id = ds.id
             AND (
               LOWER(COALESCE(sm.group_external_id, '')) = LOWER(COALESCE(sg.external_id, ''))
               OR LOWER(COALESCE(sm.group_external_id, '')) = LOWER(COALESCE(sg.dn, ''))
               OR LOWER(COALESCE(sm.group_external_id, '')) = LOWER(COALESCE(sg.name, ''))
             )
            JOIN directory_snapshot_users su
              ON su.snapshot_id = ds.id
             AND (
               LOWER(COALESCE(sm.member_external_id, '')) = LOWER(COALESCE(su.external_id, ''))
               OR LOWER(COALESCE(sm.member_external_id, '')) = LOWER(COALESCE(su.dn, ''))
               OR LOWER(COALESCE(sm.member_external_id, '')) = LOWER(COALESCE(su.username, ''))
               OR LOWER(COALESCE(sm.member_external_id, '')) = LOWER(COALESCE(su.upn, ''))
               OR LOWER(COALESCE(sm.member_external_id, '')) = LOWER(COALESCE(su.email, ''))
             )
            LEFT JOIN directory_users du
              ON du.identity_source_id = su.identity_source_id
             AND (
               LOWER(TRIM(COALESCE(du.external_id, ''))) = LOWER(TRIM(COALESCE(su.external_id, '')))
               OR LOWER(TRIM(COALESCE(du.dn, ''))) = LOWER(TRIM(COALESCE(su.dn, '')))
             )
            LEFT JOIN identity_bindings ib
              ON ib.directory_user_id = du.id
             AND ib.deleted_at IS NULL
            LEFT JOIN identities i
              ON i.id = ib.identity_id
            WHERE UPPER(COALESCE(ds.status, '')) = 'ACTIVE'
              AND (:identity_source_id IS NULL OR ds.identity_source_id = :identity_source_id)
              AND (
                LOWER(COALESCE(sg.name, '')) = LOWER(:group_ref)
                OR LOWER(COALESCE(sg.external_id, '')) = LOWER(:group_ref)
                OR LOWER(COALESCE(sg.dn, '')) = LOWER(:group_ref)
              )
            ORDER BY COALESCE(i.display_name, su.display_name, su.username, su.upn, su.email, su.external_id) ASC
            """,
            {
                "group_ref": str(group_ref or "").strip(),
                "identity_source_id": int(identity_source_id) if identity_source_id else None,
            },
        )

        out: list[dict[str, Any]] = []
        for row in rows:
            identity_id = int(row.get("identity_id") or 0)
            out.append(
                {
                    "identity_id": identity_id if identity_id > 0 else None,
                    "display_name": row.get("display_name"),
                    "username": row.get("username"),
                    "email": row.get("email"),
                    "upn": row.get("upn"),
                    "snapshot_id": int(row.get("snapshot_id") or 0) or None,
                    "source": "inherited",
                }
            )
        return out

    def list_ad_group_members(
        self,
        *,
        storage_root_id: int,
        group_ref: str,
    ) -> tuple[list[dict[str, Any]], int | None, str]:
        root_row = self._one_dict(
            """
            SELECT se.identity_source_id
            FROM storage_roots sr
            JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            WHERE sr.id = :storage_root_id
            LIMIT 1
            """,
            {"storage_root_id": int(storage_root_id)},
        )

        identity_source_id = int((root_row or {}).get("identity_source_id") or 0) or None
        active_snapshot_id = self._active_snapshot_id_for_source(identity_source_id=identity_source_id)

        rows = self._list_group_members_from_effective_memberships(
            group_ref=group_ref,
            identity_source_id=identity_source_id,
        )
        source = "inherited"

        if not rows:
            rows = self._list_group_members_from_directory_group_members(
                group_ref=group_ref,
                identity_source_id=identity_source_id,
            )
            source = "inherited"

        if not rows:
            rows = self._list_group_members_from_active_snapshot_payload(
                group_ref=group_ref,
                identity_source_id=identity_source_id,
            )
            source = "inherited"

        deduped = self._dedupe_group_member_rows(rows)
        return deduped, active_snapshot_id, source

    @staticmethod
    def _compute_expected_group_name_from_policy(
        *,
        effective_policy: dict[str, Any],
        zone_code: str,
        root_path: str,
        access_level: str,
        storage_root_id: int,
    ) -> str | None:
        level = str(access_level or "READ").strip().upper() or "READ"

        computed_name = ""
        try:
            naming = resolve_group_name_from_effective_policy(
                effective_policy=effective_policy,
                zone_code=zone_code,
                storage_root_path=root_path,
                perm=level,
            )
            computed_name = StorageRootsViewsRepo._extract_sam_account_name(naming) or ""
        except Exception:
            computed_name = ""

        if computed_name:
            return computed_name[:128]

        return None

    def project_ad_groups(
        self,
        *,
        storage_root_id: int,
        access_profiles_state: dict[str, Any],
        include_members: bool = False,
        include_expected: bool = False,
    ) -> list[dict[str, Any]]:
        root_row = self._one_dict(
            """
            SELECT
              sr.id AS storage_root_id,
              sr.root_path AS root_path,
              sr.storage_endpoint_id AS storage_endpoint_id,
              se.zone_id AS zone_id,
              se.identity_source_id AS identity_source_id,
              z.code AS zone_code
            FROM storage_roots sr
            JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            LEFT JOIN zones z ON z.id = se.zone_id
            WHERE sr.id = :storage_root_id
            LIMIT 1
            """,
            {"storage_root_id": int(storage_root_id)},
        )
        if root_row is None:
            return []

        zone_id = int(root_row.get("zone_id") or 0) or None
        storage_endpoint_id = int(root_row.get("storage_endpoint_id") or 0) or None
        identity_source_id = int(root_row.get("identity_source_id") or 0) or None
        zone_code = str(root_row.get("zone_code") or "").strip()
        root_path = str(root_row.get("root_path") or "").strip()
        acl_index = self._acl_principal_index(int(storage_root_id))

        effective_policy = resolve_effective_policy(
            self.db,
            zone_id,
            storage_endpoint_id=storage_endpoint_id,
            storage_root_id=int(storage_root_id),
        )

        items = access_profiles_state.get("attached_profiles") or []
        if not isinstance(items, list):
            items = []

        attached_profile_ids: set[int] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            profile_id = int(item.get("access_profile_id") or item.get("id") or 0)
            if profile_id > 0:
                attached_profile_ids.add(profile_id)

        if zone_id is not None:
            inherited_profiles = self._all_dicts(
                """
                SELECT
                  zap.access_profile_id,
                  ap.code,
                  ap.name,
                  ap.permission,
                  UPPER(
                    COALESCE(
                      NULLIF(ap.code, ''),
                      NULLIF(ap.permission, ''),
                      'READ'
                    )
                  ) AS access_level_code
                FROM zone_access_profiles zap
                JOIN access_profiles ap ON ap.id = zap.access_profile_id
                WHERE zap.zone_id = :zone_id
                  AND zap.is_active = 1
                  AND UPPER(
                    COALESCE(
                      NULLIF(ap.code, ''),
                      NULLIF(ap.permission, ''),
                      'READ'
                    )
                  ) IN ('READ', 'WRITE')
                ORDER BY zap.access_profile_id ASC
                """,
                {"zone_id": int(zone_id)},
            )

            for inherited in inherited_profiles:
                profile_id = int(inherited.get("access_profile_id") or 0)
                if profile_id <= 0 or profile_id in attached_profile_ids:
                    continue

                access_level = str(inherited.get("access_level_code") or "READ").strip().upper() or "READ"
                items.append(
                    {
                        "id": profile_id,
                        "access_profile_id": profile_id,
                        "code": str(inherited.get("code") or "").strip() or None,
                        "name": str(inherited.get("name") or "").strip() or None,
                        "permission": str(inherited.get("permission") or "").strip() or None,
                        "access_level": access_level,
                        "status": "NOT_CREATED",
                        "source": "INHERITED",
                        "is_materialized_on_root": False,
                        "binding_status": "inherited_candidate",
                        "approval_ready": False,
                        "group_name": None,
                        "group_external_id": None,
                        "members_count": 0,
                    }
                )

        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in items:
            if not isinstance(row, dict):
                continue

            access_level = str(row.get("access_level") or row.get("access_level_code") or "READ").strip().upper() or "READ"
            profile_id = int(row.get("access_profile_id") or row.get("id") or 0) or None
            profile_code = str(row.get("code") or row.get("name") or "").strip() or None
            profile_status = str(row.get("status") or "QUEUED").strip().upper() or "QUEUED"
            group_external_id = str(row.get("group_external_id") or "").strip() or None
            configured_group = str(row.get("group_name") or "").strip() or None

            projected_group = configured_group
            projection_source = "configured"

            if not projected_group:
                try:
                    naming = resolve_group_name_from_effective_policy(
                        effective_policy=effective_policy,
                        zone_code=zone_code,
                        storage_root_path=root_path,
                        perm=access_level,
                        profile=profile_code,
                    )
                    projected_group = self._extract_sam_account_name(naming)
                    projection_source = "template_preview"
                except Exception:
                    projected_group = None

            if not projected_group:
                continue

            dedupe_key = projected_group.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            members, active_snapshot_id, members_source = self.list_ad_group_members(
                storage_root_id=int(storage_root_id),
                group_ref=projected_group,
            )

            discovered_exists = self._ad_group_exists_for_identity_source(
                group_ref=projected_group,
                identity_source_id=identity_source_id,
            )
            failed_or_pending_statuses = {"FAILED", "ERROR", "CANCELLED", "RETRYING", "RUNNING", "QUEUED", "NOT_CREATED"}
            if profile_status in failed_or_pending_statuses:
                created = False
            else:
                created = bool(
                    discovered_exists
                    or group_external_id
                    or profile_status in {"CREATED", "SUCCEEDED", "PROVISIONED"}
                )

            group_acl_alignment = self._acl_alignment_for_group(projected_group, acl_index)

            out.append(
                {
                    "group_name": projected_group,
                    "access_level": access_level,
                    "profile_id": profile_id,
                    "profile_code": profile_code,
                    "profile_status": profile_status,
                    "error_message": (str(row.get("error_message") or "").strip() or None)
                    or (str(row.get("last_error_message") or "").strip() or None),
                    "correlation_id": row.get("correlation_id"),
                    "group_external_id": group_external_id,
                    "is_created": created,
                    "projection_source": projection_source,
                    "expected_only": False,
                    "materialized_binding_present": bool(profile_id),
                    "approval_ready": bool(profile_id),
                    "effective_profile_source": "materialized" if profile_id else "inherited_candidate",
                    "members_count": len(members),
                    "active_snapshot_id": active_snapshot_id,
                    "members_source": members_source,
                    "members": members if include_members else None,
                    **group_acl_alignment,
                }
            )

        present_levels = {
            str(row.get("access_level") or "").strip().upper()
            for row in out
            if str(row.get("access_level") or "").strip().upper() in {"READ", "WRITE"}
        }

        if include_expected:
            for level in ("READ", "WRITE"):
                if level in present_levels:
                    continue

                expected_group_name = self._compute_expected_group_name_from_policy(
                    effective_policy=effective_policy,
                    zone_code=zone_code,
                    root_path=root_path,
                    access_level=level,
                    storage_root_id=int(storage_root_id),
                )
                if not expected_group_name:
                    continue

                dedupe_key = expected_group_name.lower()
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                discovered_exists = self._ad_group_exists_for_identity_source(
                    group_ref=expected_group_name,
                    identity_source_id=identity_source_id,
                )
                members, active_snapshot_id, members_source = self.list_ad_group_members(
                    storage_root_id=int(storage_root_id),
                    group_ref=expected_group_name,
                )

                created = bool(discovered_exists or members)
                expected_acl_alignment = self._acl_alignment_for_group(expected_group_name, acl_index)

                out.append(
                    {
                        "group_name": expected_group_name,
                        "access_level": level,
                        "profile_id": None,
                        "profile_code": level,
                        "profile_status": "SUCCEEDED" if created else "NOT_CREATED",
                        "error_message": None,
                        "correlation_id": None,
                        "group_external_id": None,
                        "is_created": created,
                        "projection_source": "template_preview_default",
                        "expected_only": True,
                        "materialized_binding_present": False,
                        "approval_ready": False,
                        "effective_profile_source": "inherited_candidate",
                        "members_count": len(members),
                        "active_snapshot_id": active_snapshot_id,
                        "members_source": members_source,
                        "members": members if include_members else None,
                        **expected_acl_alignment,
                    }
                )

        out.sort(key=lambda item: (str(item.get("access_level") or ""), str(item.get("group_name") or "").lower()))
        return out
