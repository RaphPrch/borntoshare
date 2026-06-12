from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.storage_endpoint import StorageEndpoint
from app.models.storage_root import StorageRoot
from app.repositories.governance_alerts_repo import GovernanceAlertsRepo
from app.services.health_events import record_health_event


PROBE_STATUSES = {"success", "running", "failed", "unknown"}


def normalize_probe_status_value(value: object) -> str | None:
    if value is None:
        return None
    key = str(value).strip().lower()
    if not key:
        return None
    if key in PROBE_STATUSES:
        return key
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "error_code": "INVALID_PROBE_STATUS",
            "message": "last_probe_status must be one of: success, running, failed, unknown",
        },
    )


def coerce_probe_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value

    raw = str(value or "").strip()
    if raw:
        normalized = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except Exception:
            pass

    return datetime.now(timezone.utc).replace(tzinfo=None)


class ProbeResultService:
    """Persist probe/discovery outcomes and their derived operational state.

    This service deliberately owns the chain:
    probe result -> entity last_probe_* -> health event -> endpoint/root cascade
    -> governance alert reconciliation.
    """

    def __init__(self, db: Session):
        self.db = db

    def initialize_storage_root_from_endpoint_probe(
        self,
        data: dict[str, Any],
        *,
        endpoint: StorageEndpoint | None,
    ) -> dict[str, Any]:
        endpoint_probe_status = str(getattr(endpoint, "last_probe_status", "") or "").strip().lower()
        if endpoint_probe_status != "success" or data.get("last_probe_status"):
            return data

        probe_at = getattr(endpoint, "last_probe_at", None) or coerce_probe_datetime(None)
        initialized = dict(data)
        initialized["last_probe_status"] = "success"
        initialized["last_probe_at"] = probe_at
        initialized["last_probe_message"] = "endpoint_probe_ok"
        initialized["last_discovery_at"] = initialized.get("last_discovery_at") or probe_at
        return initialized

    def record_storage_root_probe(
        self,
        root: StorageRoot,
        *,
        status_value: str,
        checked_at: datetime | None = None,
        message: str | None = None,
        source_type: str,
        source_id: str | None = None,
        job_id: int | None = None,
        correlation_id: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        reconcile_alerts: bool = True,
    ) -> None:
        normalized_status = normalize_probe_status_value(status_value) or "unknown"
        probe_at = checked_at or getattr(root, "last_probe_at", None) or coerce_probe_datetime(None)
        record_health_event(
            self.db,
            entity_type="storage_root",
            entity_id=int(root.id),
            check_type="probe",
            status=normalized_status,
            message=message if message is not None else getattr(root, "last_probe_message", None),
            source_type=source_type,
            source_id=source_id or str(int(root.id)),
            job_id=job_id,
            correlation_id=correlation_id,
            checked_at=probe_at,
            metadata_json={
                "storage_root_name": getattr(root, "name", None),
                "root_path": getattr(root, "root_path", None),
                "storage_endpoint_id": int(getattr(root, "storage_endpoint_id", 0) or 0),
                **(metadata_json or {}),
            },
        )
        if normalized_status == "success":
            root.needs_revalidation = False
            root.revalidation_reason = None
        if reconcile_alerts:
            GovernanceAlertsRepo(self.db).reconcile_storage_root(int(root.id), commit=False)

    def record_storage_endpoint_probe(
        self,
        endpoint: StorageEndpoint,
        *,
        status_value: str,
        checked_at: datetime | None = None,
        message: str | None = None,
        source_type: str,
        source_id: str | None = None,
        job_id: int | None = None,
        correlation_id: str | None = None,
        cascade_to_roots: bool = True,
    ) -> list[dict[str, object]]:
        normalized_status = normalize_probe_status_value(status_value)
        if not normalized_status:
            return []

        probe_at = checked_at or getattr(endpoint, "last_probe_at", None) or coerce_probe_datetime(None)
        probe_message = str(message if message is not None else getattr(endpoint, "last_probe_message", "") or "").strip() or None

        endpoint.last_probe_status = normalized_status
        endpoint.last_probe_at = probe_at
        endpoint.last_probe_message = probe_message

        record_health_event(
            self.db,
            entity_type="storage_endpoint",
            entity_id=int(endpoint.id),
            check_type="probe",
            status=normalized_status,
            message=probe_message,
            source_type=source_type,
            source_id=source_id or str(int(endpoint.id)),
            job_id=job_id,
            correlation_id=correlation_id,
            checked_at=probe_at,
            metadata_json={
                "storage_endpoint_name": endpoint.name,
                "host": endpoint.host,
                "protocol": endpoint.protocol,
                "last_probe_status": normalized_status,
            },
        )

        if not cascade_to_roots:
            return []

        if normalized_status == "failed":
            root_message = f"Storage endpoint probe failed: {probe_message or 'Storage endpoint probe failed'}"
            impacted = self._cascade_endpoint_probe_failure_to_roots(
                endpoint_id=int(endpoint.id),
                probe_at=probe_at,
                probe_message=root_message,
            )
            for root in impacted:
                self._record_cascaded_root_health(
                    root,
                    endpoint=endpoint,
                    probe_at=probe_at,
                    status_value="failed",
                    message=root_message,
                    source_type="storage_endpoint_probe",
                    job_id=job_id,
                    correlation_id=correlation_id,
                )
            self._reconcile_impacted_roots(impacted)
            return impacted

        if normalized_status == "success":
            impacted = self._cascade_endpoint_probe_success_to_roots(
                endpoint_id=int(endpoint.id),
                probe_at=probe_at,
                probe_message=probe_message or "endpoint_probe_ok",
            )
            for root in impacted:
                self._record_cascaded_root_health(
                    root,
                    endpoint=endpoint,
                    probe_at=probe_at,
                    status_value="success",
                    message=probe_message or "endpoint_probe_ok",
                    source_type="storage_endpoint_probe",
                    job_id=job_id,
                    correlation_id=correlation_id,
                )
            self._reconcile_impacted_roots(impacted)
            return impacted

        return []

    def _record_cascaded_root_health(
        self,
        root: dict[str, object],
        *,
        endpoint: StorageEndpoint,
        probe_at: datetime,
        status_value: str,
        message: str,
        source_type: str,
        job_id: int | None,
        correlation_id: str | None,
    ) -> None:
        root_id = int(root.get("id") or 0)
        if root_id <= 0:
            return
        record_health_event(
            self.db,
            entity_type="storage_root",
            entity_id=root_id,
            check_type="reachability",
            status=status_value,
            message=message,
            source_type=source_type,
            source_id=str(int(endpoint.id)),
            job_id=job_id,
            correlation_id=correlation_id,
            checked_at=probe_at,
            metadata_json={
                "storage_root_name": root.get("name"),
                "root_path": root.get("root_path"),
                "storage_endpoint_id": int(endpoint.id),
                "storage_endpoint_name": endpoint.name,
                "previous_probe_status": root.get("previous_probe_status"),
                "previous_probe_message": root.get("previous_probe_message"),
            },
        )

    def _reconcile_impacted_roots(self, impacted: list[dict[str, object]]) -> None:
        alerts_repo = GovernanceAlertsRepo(self.db)
        for root in impacted:
            root_id = int(root.get("id") or 0)
            if root_id > 0:
                alerts_repo.reconcile_storage_root(root_id, commit=False)

    def _cascade_endpoint_probe_failure_to_roots(
        self,
        *,
        endpoint_id: int,
        probe_at: datetime,
        probe_message: str,
    ) -> list[dict[str, object]]:
        rows = (
            self.db.execute(
                text(
                    """
                    SELECT id, name, root_path, last_probe_status, last_probe_message
                    FROM storage_roots
                    WHERE storage_endpoint_id = :endpoint_id
                    """
                ),
                {"endpoint_id": int(endpoint_id)},
            )
            .mappings()
            .all()
        )

        impacted: list[dict[str, object]] = []
        for row in rows:
            root_id = int(row.get("id") or 0)
            if root_id <= 0:
                continue

            self.db.execute(
                text(
                    """
                    UPDATE storage_roots
                    SET
                      last_probe_status = 'failed',
                      last_probe_at = :probe_at,
                      last_probe_message = :probe_message
                    WHERE id = :id
                    """
                ),
                {"id": root_id, "probe_at": probe_at, "probe_message": probe_message},
            )
            impacted.append(self._impact_row(row))

        return impacted

    def _cascade_endpoint_probe_success_to_roots(
        self,
        *,
        endpoint_id: int,
        probe_at: datetime,
        probe_message: str,
    ) -> list[dict[str, object]]:
        rows = (
            self.db.execute(
                text(
                    """
                    SELECT id, name, root_path, last_probe_status, last_probe_message
                    FROM storage_roots
                    WHERE storage_endpoint_id = :endpoint_id
                      AND (
                        last_probe_status IS NULL
                        OR TRIM(last_probe_status) = ''
                        OR LOWER(last_probe_status) IN ('unknown', 'running')
                        OR (
                          LOWER(last_probe_status) = 'failed'
                          AND (
                            last_probe_message = 'root_not_discovered_or_unreachable'
                            OR last_probe_message LIKE 'Storage endpoint probe failed:%'
                          )
                        )
                      )
                    """
                ),
                {"endpoint_id": int(endpoint_id)},
            )
            .mappings()
            .all()
        )

        impacted: list[dict[str, object]] = []
        for row in rows:
            root_id = int(row.get("id") or 0)
            if root_id <= 0:
                continue

            self.db.execute(
                text(
                    """
                    UPDATE storage_roots
                    SET
                      last_probe_status = 'success',
                      last_probe_at = :probe_at,
                      last_probe_message = :probe_message,
                      last_discovery_at = COALESCE(last_discovery_at, :probe_at)
                    WHERE id = :id
                    """
                ),
                {"id": root_id, "probe_at": probe_at, "probe_message": probe_message},
            )
            impacted.append(self._impact_row(row))

        return impacted

    def mark_roots_need_revalidation(
        self,
        *,
        endpoint: StorageEndpoint,
        reason: str,
        job_id: int | None = None,
        correlation_id: str | None = None,
    ) -> list[dict[str, object]]:
        probe_at = coerce_probe_datetime(None)
        reason_value = str(reason or "").strip()[:512] or "storage_endpoint_configuration_changed"
        rows = (
            self.db.execute(
                text(
                    """
                    SELECT id, name, root_path, last_probe_status, last_probe_message
                    FROM storage_roots
                    WHERE storage_endpoint_id = :endpoint_id
                      AND deleted_at IS NULL
                    """
                ),
                {"endpoint_id": int(endpoint.id)},
            )
            .mappings()
            .all()
        )

        impacted: list[dict[str, object]] = []
        for row in rows:
            root_id = int(row.get("id") or 0)
            if root_id <= 0:
                continue
            self.db.execute(
                text(
                    """
                    UPDATE storage_roots
                    SET
                      needs_revalidation = 1,
                      revalidation_reason = :reason,
                      last_probe_status = CASE
                        WHEN LOWER(COALESCE(last_probe_status, '')) = 'success' THEN 'unknown'
                        ELSE last_probe_status
                      END,
                      last_probe_message = :reason
                    WHERE id = :id
                    """
                ),
                {"id": root_id, "reason": reason_value},
            )
            impacted_row = self._impact_row(row)
            impacted.append(impacted_row)
            record_health_event(
                self.db,
                entity_type="storage_root",
                entity_id=root_id,
                check_type="revalidation",
                status="unknown",
                message=reason_value,
                source_type="storage_endpoint_update",
                source_id=str(int(endpoint.id)),
                job_id=job_id,
                correlation_id=correlation_id,
                checked_at=probe_at,
                metadata_json={
                    "storage_root_name": row.get("name"),
                    "root_path": row.get("root_path"),
                    "storage_endpoint_id": int(endpoint.id),
                    "storage_endpoint_name": endpoint.name,
                    "reason": reason_value,
                },
            )

        self._reconcile_impacted_roots(impacted)
        return impacted

    @staticmethod
    def _impact_row(row: Any) -> dict[str, object]:
        return {
            "id": int(row.get("id") or 0),
            "name": str(row.get("name") or "").strip() or None,
            "root_path": str(row.get("root_path") or "").strip() or None,
            "previous_probe_status": str(row.get("last_probe_status") or "").strip().lower() or None,
            "previous_probe_message": str(row.get("last_probe_message") or "").strip() or None,
        }
