from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.storage_endpoint import StorageEndpoint
from app.models.storage_root import StorageRoot
from app.repositories.directory_snapshots_repo import DirectorySnapshotsRepo
from app.repositories.provisioning_jobs_repo import ProvisioningJobsRepo
from app.repositories.storage_root_access_profiles_repo import StorageRootAccessProfilesRepo
from app.services.directory_effective_memberships_service import DirectoryEffectiveMembershipsService
from app.services.directory_projection_service import DirectoryProjectionService
from app.services.health_events import record_health_event
from app.services.probe_results import ProbeResultService
from app.services.provisioning_ou_sql import effective_group_ou_case_sql
from app.security.audit_hash import compute_event_hash, scrub_secrets
from app.security.internal_auth import require_internal
from app.utils.status_validation import ensure_transition, normalize_status, validate_profile_invariants


router = APIRouter(prefix="/internal/provisioning", tags=["internal-provisioning"])

MAX_RETRY_ATTEMPTS = 5


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UpsertStorageRootAccessProfilePayload(BaseModel):
    storage_root_id: int = Field(..., gt=0)
    access_level_code: str = Field(..., min_length=1, max_length=32)
    permission_hash: str = Field(..., min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=190)
    access_profile_id: int | None = Field(default=None, gt=0)
    group_name: str | None = Field(default=None, max_length=128)
    status: str = Field(default="CREATED", max_length=32)
    actor_ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=256)
    correlation_id: str | None = Field(default=None, max_length=128)


class CreateProvisioningJobPayload(BaseModel):
    correlation_id: str = Field(..., min_length=8, max_length=128)
    job_type: str = Field(..., min_length=1, max_length=32)
    action: str | None = Field(default=None, max_length=64)
    status: str = Field(default="QUEUED", max_length=32)
    storage_root_access_profile_id: int | None = Field(default=None, gt=0)
    identity_source_id: int | None = Field(default=None, gt=0)
    payload_json: dict | None = None
    result_json: dict | None = None
    metrics_json: dict | None = None
    error_json: dict | None = None
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class JobStartPayload(BaseModel):
    actor_ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=256)
    correlation_id: str = Field(..., min_length=8, max_length=128)
    lock_owner: str | None = Field(default=None, max_length=100)
    capsule_execution_id: int | None = Field(default=None, gt=0)


class JobRequeuePayload(BaseModel):
    correlation_id: str = Field(..., min_length=8, max_length=128)
    reason: str | None = Field(default=None, max_length=128)
    force: bool = False


class JobCancelPayload(BaseModel):
    correlation_id: str = Field(..., min_length=8, max_length=128)
    reason: str | None = Field(default=None, max_length=512)
    requested_by: str | None = Field(default=None, max_length=128)
    source: str | None = Field(default="ui", max_length=64)


class JobWatchdogRepublishPayload(BaseModel):
    correlation_id: str = Field(..., min_length=8, max_length=128)
    reason: str | None = Field(default=None, max_length=128)


class JobCompletePayload(BaseModel):
    action: str | None = Field(default=None, max_length=64)
    result_json: dict | None = None
    metrics_json: dict | None = None
    actor_ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=256)
    correlation_id: str = Field(..., min_length=8, max_length=128)


class JobFailPayload(BaseModel):
    action: str | None = Field(default=None, max_length=64)
    error_code: str = Field(..., min_length=1, max_length=64)
    error_message: str | None = None
    result_json: dict | None = None
    metrics_json: dict | None = None
    error_json: dict | None = None
    actor_ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=256)
    correlation_id: str = Field(..., min_length=8, max_length=128)


class ProfileProvisionedPayload(BaseModel):
    group_external_id: str = Field(..., min_length=1, max_length=190)
    correlation_id: str = Field(..., min_length=8, max_length=128)
    actor_ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=256)


class ProfileFailedPayload(BaseModel):
    error_code: str = Field(..., min_length=1, max_length=64)
    error_message: str | None = None
    correlation_id: str = Field(..., min_length=8, max_length=128)
    actor_ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=256)


class CompleteAndApplyPayload(BaseModel):
    outcome: str = Field(..., min_length=1, max_length=16)
    action: str | None = Field(default=None, max_length=64)
    result_json: dict | None = None
    metrics_json: dict | None = None
    error_json: dict | None = None
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = None

    profile_id: int = Field(..., gt=0)
    group_external_id: str | None = Field(default=None, max_length=190)

    event_type: str = Field(..., min_length=1, max_length=64)
    event_payload_json: dict | None = None

    actor_ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=256)
    correlation_id: str = Field(..., min_length=8, max_length=128)


def _retry_backoff_minutes(attempt_count: int) -> int:
    table = [1, 5, 15, 60]
    idx = max(0, min(int(attempt_count) - 1, len(table) - 1))
    return table[idx]


def _next_retry_attempt_count(job_attempt_count: int | None, profile_attempt_count: int | None) -> int:
    return max(int(job_attempt_count or 0), int(profile_attempt_count or 0)) + 1


def _require_correlation(correlation_id: str) -> str:
    value = str(correlation_id or "").strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="correlation_id is required")
    return value


def _normalize_access_level(raw: str) -> str:
    value = str(raw or "").strip().upper()
    if value not in {"READ", "WRITE"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="access_level must be READ or WRITE")
    return value


def _resolve_access_profile_id_for_level(db: Session, *, access_level_code: str) -> int:
    level = _normalize_access_level(access_level_code)
    row = db.execute(
        text(
            """
            SELECT ap.id
            FROM access_profiles ap
            WHERE UPPER(
              COALESCE(
                NULLIF(ap.code, ''),
                NULLIF(ap.permission, ''),
                'READ'
              )
            ) = :access_level_code
            ORDER BY
              CASE WHEN UPPER(COALESCE(NULLIF(ap.code, ''), '')) = :access_level_code THEN 0 ELSE 1 END,
              CASE WHEN COALESCE(ap.active, 1) = 1 THEN 0 ELSE 1 END,
              ap.id ASC
            LIMIT 1
            """
        ),
        {"access_level_code": level},
    ).mappings().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No access_profiles template found for access_level={level}",
        )
    return int(row.get("id") or 0)


def _write_governance_event(
    db: Session,
    *,
    event_type: str,
    target_type: str,
    target_id: int | None,
    storage_root_access_profile_id: int | None = None,
    provisioning_job_id: int | None = None,
    status_value: str | None = None,
    payload_json: dict | None = None,
    actor_ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    prev_row = db.execute(text("SELECT event_hash FROM governance_events ORDER BY id DESC LIMIT 1")).mappings().first()
    prev_hash = str((prev_row or {}).get("event_hash") or "").strip() or None
    sanitized_payload = scrub_secrets(payload_json or {})
    event_payload = {
        "event_type": event_type,
        "target_type": target_type,
        "target_id": target_id,
        "storage_root_access_profile_id": storage_root_access_profile_id,
        "provisioning_job_id": provisioning_job_id,
        "status": status_value,
        "payload_json": sanitized_payload,
        "actor_ip": actor_ip,
        "user_agent": user_agent,
    }
    event_hash = compute_event_hash(prev_hash, event_payload)

    db.execute(
        text(
            """
            INSERT INTO governance_events (
              event_type,
              target_type,
              target_id,
              storage_root_access_profile_id,
              provisioning_job_id,
              status,
              payload_json,
              prev_hash,
              event_hash,
              actor_ip,
              user_agent
            ) VALUES (
              :event_type,
              :target_type,
              :target_id,
              :storage_root_access_profile_id,
              :provisioning_job_id,
              :status,
              :payload_json,
              :prev_hash,
              :event_hash,
              :actor_ip,
              :user_agent
            )
            """
        ),
        {
            "event_type": event_type,
            "target_type": target_type,
            "target_id": target_id,
            "storage_root_access_profile_id": storage_root_access_profile_id,
            "provisioning_job_id": provisioning_job_id,
            "status": status_value,
            "payload_json": json.dumps(sanitized_payload, ensure_ascii=False),
            "prev_hash": prev_hash,
            "event_hash": event_hash,
            "actor_ip": actor_ip,
            "user_agent": user_agent,
        },
    )


def _probe_result_message(result_json: dict | None, fallback: str | None = None) -> str | None:
    if isinstance(result_json, dict):
        direct = str(result_json.get("message") or "").strip()
        if direct:
            return direct[:512]

        details = result_json.get("details") if isinstance(result_json.get("details"), dict) else {}
        details_message = str(details.get("message") or "").strip()
        if details_message:
            return details_message[:512]

    alt = str(fallback or "").strip()
    return alt[:512] if alt else None


def _persist_identity_source_probe_result(
    db: Session,
    *,
    job_type: str | None,
    identity_source_id: int | None,
    result_json: dict | None,
    fallback_message: str | None = None,
    status_value: str | None = None,
    job_id: int | None = None,
    correlation_id: str | None = None,
) -> None:
    if str(job_type or "").strip().upper() != "LDAP_TEST":
        return

    source_id = int(identity_source_id or 0)
    if source_id <= 0:
        return

    checked_at = _utcnow_naive()
    message = _probe_result_message(result_json, fallback_message)
    result_success = result_json.get("success") if isinstance(result_json, dict) else None
    health_status = (
        "success"
        if result_success is True
        else "failed"
        if result_success is False or fallback_message
        else status_value
        or "unknown"
    )
    source_status = (
        "success"
        if str(health_status or "").strip().lower() == "success"
        else "error"
        if str(health_status or "").strip().lower() == "failed"
        else "checking"
        if str(health_status or "").strip().lower() == "running"
        else None
    )

    db.execute(
        text(
            """
            UPDATE identity_sources
            SET last_probe_at = :last_probe_at,
                last_probe_message = :last_probe_message,
                status = COALESCE(:status, status),
                updated_at = :updated_at
            WHERE id = :identity_source_id
            """
        ),
        {
            "identity_source_id": source_id,
            "last_probe_at": checked_at,
            "last_probe_message": message,
            "status": source_status,
            "updated_at": checked_at,
        },
    )
    record_health_event(
        db,
        entity_type="identity_source",
        entity_id=source_id,
        check_type="probe",
        status=health_status,
        message=message,
        source_type="provisioning_job",
        source_id=str(job_id) if job_id else None,
        job_id=job_id,
        correlation_id=correlation_id,
        checked_at=checked_at,
        metadata_json={
            "job_type": str(job_type or "").strip().upper(),
            "result": result_json or {},
        },
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_int(value: Any) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _as_list_of_dict(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _parse_status_csv(raw: str | None) -> list[str]:
    value = str(raw or "").strip()
    if not value:
        return []
    statuses: list[str] = []
    seen: set[str] = set()
    for part in value.split(","):
        token = str(part or "").strip()
        if not token:
            continue
        normalized = normalize_status(token)
        if normalized in seen:
            continue
        seen.add(normalized)
        statuses.append(normalized)
    return statuses


def _extract_storage_endpoint_id_from_probe(
    *,
    job_payload_json: dict | None,
    result_json: dict | None,
) -> int | None:
    payload_json = _as_dict(job_payload_json)
    nested_payload = _as_dict(payload_json.get("payload"))
    target = _as_dict(nested_payload.get("target"))
    context = _as_dict(nested_payload.get("context"))
    details = _as_dict(_as_dict(result_json).get("details"))

    return (
        _as_int(details.get("storage_endpoint_id"))
        or _as_int(target.get("storage_endpoint_id"))
        or _as_int(context.get("storage_endpoint_id"))
    )


def _extract_storage_root_id_from_probe(
    *,
    job_payload_json: dict | None,
    result_json: dict | None,
) -> int | None:
    payload_json = _as_dict(job_payload_json)
    nested_payload = _as_dict(payload_json.get("payload"))
    target = _as_dict(nested_payload.get("target"))
    context = _as_dict(nested_payload.get("context"))
    details = _as_dict(_as_dict(result_json).get("details"))

    return (
        _as_int(details.get("storage_root_id"))
        or _as_int(target.get("storage_root_id"))
        or _as_int(context.get("storage_root_id"))
    )


def _persist_storage_endpoint_probe_result(
    db: Session,
    *,
    job_row: Any,
    result_json: dict | None,
    fallback_message: str | None = None,
    status_value: str | None = None,
    correlation_id: str | None = None,
) -> None:
    if str(getattr(job_row, "job_type", "") or "").strip().upper() != "SMB_PROBE":
        return
    if str(getattr(job_row, "action", "") or "").strip() != "test_smb_ntlm":
        return

    endpoint_id = _extract_storage_endpoint_id_from_probe(
        job_payload_json=getattr(job_row, "payload_json", None),
        result_json=result_json,
    )
    if not endpoint_id:
        return

    endpoint = db.get(StorageEndpoint, int(endpoint_id))
    if endpoint is None:
        return

    result = _as_dict(result_json)
    details = _as_dict(result.get("details"))
    result_success = result.get("success")
    normalized_status = (
        "success"
        if result_success is True
        else "failed"
        if result_success is False or fallback_message
        else str(status_value or "unknown").strip().lower()
    )
    message = _probe_result_message(result, fallback_message)

    ProbeResultService(db).record_storage_endpoint_probe(
        endpoint,
        status_value=normalized_status,
        checked_at=_utcnow_naive(),
        message=message,
        source_type="provisioning_job",
        source_id=str(int(getattr(job_row, "id", 0) or 0)),
        job_id=int(getattr(job_row, "id", 0) or 0) or None,
        correlation_id=correlation_id,
        cascade_to_roots=False,
    )
    record_health_event(
        db,
        entity_type="storage_endpoint",
        entity_id=int(endpoint_id),
        check_type="probe_details",
        status=normalized_status,
        message=message,
        source_type="provisioning_job",
        source_id=str(int(getattr(job_row, "id", 0) or 0)),
        job_id=int(getattr(job_row, "id", 0) or 0) or None,
        correlation_id=correlation_id,
        checked_at=_utcnow_naive(),
        metadata_json={
            "job_type": "SMB_PROBE",
            "checks": details.get("checks") if isinstance(details.get("checks"), list) else [],
            "failure_code": details.get("failure_code"),
            "discovery_complete": details.get("discovery_complete"),
        },
    )


def _persist_storage_root_probe_result(
    db: Session,
    *,
    job_row: Any,
    result_json: dict | None,
    fallback_message: str | None = None,
    status_value: str | None = None,
    correlation_id: str | None = None,
) -> None:
    if str(getattr(job_row, "action", "") or "").strip() != "test_smb_root_access":
        return

    root_id = _extract_storage_root_id_from_probe(
        job_payload_json=getattr(job_row, "payload_json", None),
        result_json=result_json,
    )
    if not root_id:
        return

    root = db.get(StorageRoot, int(root_id))
    if root is None:
        return

    result = _as_dict(result_json)
    details = _as_dict(result.get("details"))
    result_success = result.get("success")
    normalized_status = (
        "success"
        if result_success is True
        else "failed"
        if result_success is False or fallback_message
        else str(status_value or "unknown").strip().lower()
    )
    message = _probe_result_message(result, fallback_message)
    checked_at = _utcnow_naive()

    root.last_probe_status = normalized_status
    root.last_probe_at = checked_at
    root.last_probe_message = message
    if normalized_status == "success":
        root.needs_revalidation = False
        root.revalidation_reason = None
        permissions = _as_list_of_dict(result.get("permissions")) or _as_list_of_dict(details.get("permissions"))
        checks = details.get("checks") if isinstance(details.get("checks"), list) else []
        acl_check = next(
            (
                item
                for item in checks
                if isinstance(item, dict) and str(item.get("name") or "").strip() == "root_acl"
            ),
            None,
        )
        acl_check_succeeded = str((acl_check or {}).get("status") or "").strip().lower() == "success"
        content_size_bytes = None
        for candidate in (
            details.get("content_size_bytes"),
            details.get("estimated_size_bytes"),
            result.get("content_size_bytes"),
            result.get("estimated_size_bytes"),
        ):
            if candidate is None or candidate == "":
                continue
            try:
                parsed = int(candidate)
            except (TypeError, ValueError):
                continue
            if parsed < 0:
                continue
            content_size_bytes = parsed
            break
        content_scanned_at = (
            str(details.get("content_updated_at") or "").strip()
            or str(details.get("last_content_scan_at") or "").strip()
            or checked_at.isoformat()
        )
        if permissions or acl_check_succeeded:
            root.discovered_permissions_json = {
                "discovered_at": checked_at.isoformat(),
                "source": "storage_root_probe",
                "probe_job_id": int(getattr(job_row, "id", 0) or 0) or None,
                "permissions": permissions,
                "permissions_count": len(permissions),
                "content_size_bytes": content_size_bytes,
                "content_updated_at": content_scanned_at,
            }
        endpoint_id = int(getattr(root, "storage_endpoint_id", 0) or 0)
        if endpoint_id > 0:
            endpoint = db.get(StorageEndpoint, endpoint_id)
            if endpoint is not None:
                ProbeResultService(db).record_storage_endpoint_probe(
                    endpoint,
                    status_value="success",
                    checked_at=checked_at,
                    message="endpoint_alive_via_successful_root_probe",
                    source_type="storage_root_probe",
                    source_id=str(int(getattr(root, "id", 0) or 0)),
                    job_id=int(getattr(job_row, "id", 0) or 0) or None,
                    correlation_id=correlation_id,
                    cascade_to_roots=False,
                )

    ProbeResultService(db).record_storage_root_probe(
        root,
        status_value=normalized_status,
        checked_at=checked_at,
        message=message,
        source_type="provisioning_job",
        source_id=str(int(getattr(job_row, "id", 0) or 0)),
        job_id=int(getattr(job_row, "id", 0) or 0) or None,
        correlation_id=correlation_id,
        metadata_json={
            "job_type": "SMB_PROBE",
            "action": "test_smb_root_access",
            "checks": details.get("checks") if isinstance(details.get("checks"), list) else [],
            "failure_code": details.get("failure_code"),
            "permissions_count": int(details.get("permissions_count") or len(_as_list_of_dict(details.get("permissions")))),
        },
    )


def _parse_job_type_csv(raw: str | None) -> list[str]:
    value = str(raw or "").strip()
    if not value:
        return []
    job_types: list[str] = []
    seen: set[str] = set()
    for part in value.split(","):
        token = str(part or "").strip().upper()
        if not token or token in seen:
            continue
        seen.add(token)
        job_types.append(token)
    return job_types


def _extract_directory_snapshot_inputs(
    *,
    job_payload_json: dict | None,
    result_json: dict | None,
) -> tuple[int | None, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    payload_json = _as_dict(job_payload_json)
    result = _as_dict(result_json)

    nested_payload = _as_dict(payload_json.get("payload"))
    details = _as_dict(result.get("details"))
    result_payload = _as_dict(result.get("payload"))
    if not result_payload:
        result_payload = _as_dict(details.get("payload"))

    snapshot_id = int(
        result.get("snapshot_id")
        or details.get("snapshot_id")
        or nested_payload.get("snapshot_id")
        or 0
    ) or None

    users = _as_list_of_dict(result_payload.get("users"))
    groups = _as_list_of_dict(result_payload.get("groups"))
    memberships = _as_list_of_dict(result_payload.get("memberships"))
    return snapshot_id, users, groups, memberships


def _apply_directory_snapshot_success(
    db: Session,
    *,
    job_row: Any,
    result_json: dict | None,
) -> None:
    snapshot_id, users, groups, memberships = _extract_directory_snapshot_inputs(
        job_payload_json=getattr(job_row, "payload_json", None),
        result_json=result_json,
    )
    if not snapshot_id:
        return

    repo = DirectorySnapshotsRepo(db)
    counts = repo.bulk_upsert(
        snapshot_id=int(snapshot_id),
        users=users,
        groups=groups,
        memberships=memberships,
    )

    repo.patch_status(
        snapshot_id=int(snapshot_id),
        status="SUCCEEDED",
        summary_json={
            "phase": "collected",
            "job_id": int(getattr(job_row, "id", 0) or 0),
            "counts": counts,
        },
        error_message=None,
    )

    activated = DirectoryProjectionService(db).activate_snapshot(
        snapshot_id=int(snapshot_id),
        activated_by="capsule.directory_snapshot.complete",
    )
    if activated:
        DirectoryEffectiveMembershipsService(db).rebuild_for_snapshot(snapshot_id=int(snapshot_id))


def _apply_directory_snapshot_failure(
    db: Session,
    *,
    job_row: Any,
    error_code: str | None,
    error_message: str | None,
) -> None:
    snapshot_id, _, _, _ = _extract_directory_snapshot_inputs(
        job_payload_json=getattr(job_row, "payload_json", None),
        result_json=None,
    )
    if not snapshot_id:
        return

    repo = DirectorySnapshotsRepo(db)
    repo.patch_status(
        snapshot_id=int(snapshot_id),
        status="FAILED",
        summary_json={
            "phase": "failed",
            "job_id": int(getattr(job_row, "id", 0) or 0),
            "error_code": str(error_code or "").strip() or None,
        },
        error_message=str(error_message or "").strip() or str(error_code or "snapshot_failed"),
    )


@router.get("/storage-roots/{storage_root_id}/context", dependencies=[require_internal({"profiles:write"})])
def get_storage_root_provisioning_context(storage_root_id: int, db: Session = Depends(get_db)):
    effective_group_ou_sql = effective_group_ou_case_sql()
    row = db.execute(
        text(
            f"""
            SELECT
              sr.id AS storage_root_id,
              sr.name AS storage_root_name,
              sr.root_path,
              se.id AS storage_endpoint_id,
              se.zone_id,
              se.host,
              se.port AS endpoint_port,
              se.protocol AS endpoint_protocol,
              se.sub_ou_dn,
              se.bind_dn AS endpoint_bind_dn,
              se.bind_password_ref AS endpoint_bind_password_ref,
              se.identity_source_id,
              UPPER(COALESCE(NULLIF(ids.type, ''), 'ad')) AS identity_source_kind,
              ids.host AS identity_source_host,
              ids.port AS identity_source_port,
              ids.protocol AS identity_source_protocol,
              ids.bind_dn AS identity_source_bind_dn,
              ids.bind_password_ref AS identity_source_bind_password_ref,
              ids.base_dn AS identity_source_base_dn,
              ids.domain_name,
              CASE
                WHEN COALESCE(ids.write_enabled, 0) = 1 THEN 1
                WHEN COALESCE(
                  NULLIF(ids.bind_password_ref, ''),
                  NULLIF(se.bind_password_ref, '')
                ) IS NOT NULL THEN 1
                ELSE 0
              END AS write_enabled,
              ids.default_group_ou_dn,
              zpp.base_ou_dn AS zone_default_group_ou_dn,
              {effective_group_ou_sql} AS effective_group_ou_dn
            FROM storage_roots sr
            JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            LEFT JOIN zone_provisioning_policy zpp ON zpp.zone_id = se.zone_id
            LEFT JOIN identity_sources ids ON ids.id = se.identity_source_id
            WHERE sr.id = :id
            LIMIT 1
            """
        ),
        {"id": int(storage_root_id)},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root not found")
    return dict(row)


@router.post("/storage-root-access-profiles", dependencies=[require_internal({"profiles:write"})])
def upsert_storage_root_access_profile(payload: UpsertStorageRootAccessProfilePayload, db: Session = Depends(get_db)):
    access_level_code = _normalize_access_level(payload.access_level_code)
    repo = StorageRootAccessProfilesRepo(db)
    resolved_access_profile_id = int(payload.access_profile_id or 0)
    if resolved_access_profile_id <= 0:
        resolved_access_profile_id = _resolve_access_profile_id_for_level(db, access_level_code=access_level_code)
    resolved_group_name = str(payload.group_name or "").strip()
    if not resolved_group_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="group_name is required for provisioning profile upsert",
        )

    if access_level_code in {"READ", "WRITE"}:
        existing_level = db.execute(
            text(
                """
                SELECT id
                FROM storage_root_access_profiles
                WHERE storage_root_id = :storage_root_id
                  AND access_level_code = :access_level_code
                  AND deleted_at IS NULL
                LIMIT 1
                """
            ),
            {
                "storage_root_id": int(payload.storage_root_id),
                "access_level_code": access_level_code,
            },
        ).mappings().first()
        if existing_level:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{access_level_code} profile already exists for this storage root",
            )

    existing = repo.find_by_root_and_permission_hash(
        storage_root_id=int(payload.storage_root_id),
        permission_hash=str(payload.permission_hash),
    )
    if existing:
        return {"created": False, "data": repo.to_dict(existing)}

    created = repo.create(
        data={
            "storage_root_id": int(payload.storage_root_id),
            "access_profile_id": resolved_access_profile_id,
            "group_name": resolved_group_name,
            "name": payload.name,
            "access_level_code": access_level_code,
            "permission_hash": payload.permission_hash,
            "status": payload.status,
            "active": True,
        }
    )

    _write_governance_event(
        db,
        event_type="profile_created",
        target_type="storage_root_access_profile",
        target_id=int(created.id),
        storage_root_access_profile_id=int(created.id),
        status_value=str(created.status),
        payload_json={
            "storage_root_id": int(payload.storage_root_id),
            "access_level_code": access_level_code,
            "permission_hash": payload.permission_hash,
        },
        actor_ip=payload.actor_ip,
        user_agent=payload.user_agent,
    )
    if hasattr(db, "commit"):
        db.commit()
    return {"created": True, "data": repo.to_dict(created)}


@router.post("/storage-root-access-profiles/{profile_id}/queue", dependencies=[require_internal({"profiles:write"})])
def queue_storage_root_access_profile(
    profile_id: int,
    payload: JobStartPayload,
    db: Session = Depends(get_db),
):
    _ = _require_correlation(payload.correlation_id)
    repo = StorageRootAccessProfilesRepo(db)
    row = repo.get_by_id(int(profile_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root access profile not found")

    row = repo.update(
        obj=row,
        updates={
            "status": "QUEUED",
            "next_retry_at": None,
        },
    )
    return repo.to_dict(row)


@router.get("/storage-root-access-profiles/{profile_id}", dependencies=[require_internal({"profiles:write"})])
def get_storage_root_access_profile(profile_id: int, db: Session = Depends(get_db)):
    repo = StorageRootAccessProfilesRepo(db)
    row = repo.get_by_id(int(profile_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root access profile not found")
    return repo.to_dict(row)


@router.get("/storage-root-access-profiles", dependencies=[require_internal({"profiles:write"})])
def list_storage_root_access_profiles(
    storage_root_id: int,
    access_level_code: str | None = None,
    db: Session = Depends(get_db),
):
    repo = StorageRootAccessProfilesRepo(db)
    rows = repo.list_by_root(storage_root_id=int(storage_root_id), access_level_code=access_level_code)
    return [repo.to_dict(r) for r in rows]


@router.post("/storage-root-access-profiles/{profile_id}/mark-provisioned", dependencies=[require_internal({"profiles:write", "events:write"})])
def mark_storage_root_access_profile_provisioned(
    profile_id: int,
    payload: ProfileProvisionedPayload,
    db: Session = Depends(get_db),
):
    repo = StorageRootAccessProfilesRepo(db)
    row = repo.get_by_id(int(profile_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root access profile not found")

    next_status = ensure_transition(current=row.status, next_status="SUCCEEDED")
    validate_profile_invariants(status_value=next_status, group_external_id=payload.group_external_id, error_code=None)

    row = repo.update(
        obj=row,
        updates={
            "status": next_status,
            "group_external_id": payload.group_external_id,
            "error_code": None,
            "error_message": None,
        },
    )

    _write_governance_event(
        db,
        event_type="profile_provisioning_success",
        target_type="storage_root_access_profile",
        target_id=int(profile_id),
        storage_root_access_profile_id=int(profile_id),
        status_value="SUCCEEDED",
        payload_json={"group_external_id": payload.group_external_id, "correlation_id": payload.correlation_id},
        actor_ip=payload.actor_ip,
        user_agent=payload.user_agent,
    )
    db.commit()
    return repo.to_dict(row)


@router.post("/storage-root-access-profiles/{profile_id}/mark-failed", dependencies=[require_internal({"profiles:write", "events:write"})])
def mark_storage_root_access_profile_failed(
    profile_id: int,
    payload: ProfileFailedPayload,
    db: Session = Depends(get_db),
):
    repo = StorageRootAccessProfilesRepo(db)
    row = repo.get_by_id(int(profile_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root access profile not found")

    next_status = ensure_transition(current=row.status, next_status="FAILED")
    validate_profile_invariants(status_value=next_status, group_external_id=row.group_external_id, error_code=payload.error_code)

    row = repo.update(
        obj=row,
        updates={
            "status": next_status,
            "error_code": payload.error_code,
            "error_message": payload.error_message,
        },
    )

    _write_governance_event(
        db,
        event_type="profile_provisioning_failed",
        target_type="storage_root_access_profile",
        target_id=int(profile_id),
        storage_root_access_profile_id=int(profile_id),
        status_value="FAILED",
        payload_json={
            "error_code": payload.error_code,
            "error_message": payload.error_message,
            "correlation_id": payload.correlation_id,
        },
        actor_ip=payload.actor_ip,
        user_agent=payload.user_agent,
    )
    db.commit()
    return repo.to_dict(row)


@router.post("/jobs", dependencies=[require_internal({"jobs:write"})])
def create_provisioning_job(payload: CreateProvisioningJobPayload, db: Session = Depends(get_db)):
    repo = ProvisioningJobsRepo(db)
    exists = repo.get_by_correlation(payload.correlation_id)
    if exists:
        return {"created": False, "data": repo.to_dict(exists)}

    created = repo.create(
        data={
            "correlation_id": payload.correlation_id,
            "job_type": payload.job_type,
            "action": payload.action,
            "status": payload.status,
            "storage_root_access_profile_id": payload.storage_root_access_profile_id,
            "identity_source_id": payload.identity_source_id,
            "payload_json": payload.payload_json,
            "result_json": payload.result_json,
            "metrics_json": payload.metrics_json,
            "error_json": payload.error_json,
            "error_code": payload.error_code,
            "error_message": payload.error_message,
            "started_at": payload.started_at,
            "finished_at": payload.finished_at,
        }
    )
    return {"created": True, "data": repo.to_dict(created)}


@router.get("/jobs", dependencies=[require_internal({"jobs:read"})])
def list_provisioning_jobs(
    status: str | None = None,
    job_type: str | None = None,
    identity_source_id: int | None = None,
    storage_root_access_profile_id: int | None = None,
    active_only: bool = False,
    updated_before_seconds: int | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    statuses = _parse_status_csv(status)
    lim = max(1, min(int(limit), 1000))
    conds: list[str] = ["1=1"]
    params: dict[str, Any] = {"lim": lim}

    if statuses:
        placeholders: list[str] = []
        for i, item in enumerate(statuses):
            key = f"status_{i}"
            placeholders.append(f":{key}")
            params[key] = item
        conds.append(f"UPPER(COALESCE(pj.status, '')) IN ({', '.join(placeholders)})")

    if active_only:
        conds.append("UPPER(COALESCE(pj.status, '')) IN ('CREATED','QUEUED','RUNNING','RETRYING')")

    job_types = _parse_job_type_csv(job_type)
    if job_types:
        placeholders: list[str] = []
        for i, item in enumerate(job_types):
            key = f"job_type_{i}"
            placeholders.append(f":{key}")
            params[key] = item
        conds.append(f"UPPER(COALESCE(pj.job_type, '')) IN ({', '.join(placeholders)})")

    if int(identity_source_id or 0) > 0:
        conds.append("pj.identity_source_id = :identity_source_id")
        params["identity_source_id"] = int(identity_source_id)

    if int(storage_root_access_profile_id or 0) > 0:
        conds.append("pj.storage_root_access_profile_id = :storage_root_access_profile_id")
        params["storage_root_access_profile_id"] = int(storage_root_access_profile_id)

    if int(updated_before_seconds or 0) > 0:
        conds.append("TIMESTAMPDIFF(SECOND, COALESCE(pj.updated_at, pj.created_at), UTC_TIMESTAMP()) >= :updated_before_seconds")
        params["updated_before_seconds"] = int(updated_before_seconds)

    rows = db.execute(
        text(
            f"""
            SELECT
              pj.id,
              pj.correlation_id,
              pj.job_type,
              pj.action,
              UPPER(COALESCE(pj.status, 'QUEUED')) AS status,
              pj.storage_root_access_profile_id,
              pj.identity_source_id,
              pj.payload_json,
              pj.result_json,
              pj.metrics_json,
              pj.error_json,
              pj.error_code,
              pj.error_message,
              pj.started_at,
              pj.finished_at,
              pj.created_at,
              pj.updated_at,
              TIMESTAMPDIFF(SECOND, pj.created_at, UTC_TIMESTAMP()) AS queue_age_seconds,
              CAST(
                COALESCE(
                  JSON_UNQUOTE(JSON_EXTRACT(pj.metrics_json, '$.watchdog_republish_count')),
                  '0'
                ) AS UNSIGNED
              ) AS watchdog_republish_count
            FROM provisioning_jobs pj
            WHERE {' AND '.join(conds)}
            ORDER BY pj.updated_at DESC, pj.id DESC
            LIMIT :lim
            """
        ),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


@router.get("/jobs/by-correlation/{correlation_id}", dependencies=[require_internal({"jobs:read"})])
def get_provisioning_job_by_correlation(correlation_id: str, db: Session = Depends(get_db)):
    repo = ProvisioningJobsRepo(db)
    row = repo.get_by_correlation(correlation_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provisioning job not found")
    return repo.to_dict(row)


@router.get("/jobs/by-profile/{profile_id}", dependencies=[require_internal({"jobs:read"})])
def get_latest_provisioning_job_by_profile(profile_id: int, db: Session = Depends(get_db)):
    repo = ProvisioningJobsRepo(db)
    row = repo.get_latest_by_profile(int(profile_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provisioning job not found")
    return repo.to_dict(row)


@router.get("/jobs/{job_id}", dependencies=[require_internal({"jobs:read"})])
def get_provisioning_job_by_id(job_id: int, db: Session = Depends(get_db)):
    repo = ProvisioningJobsRepo(db)
    row = repo.get_by_id(int(job_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provisioning job not found")
    return repo.to_dict(row)


@router.post("/jobs/{job_id}/start", dependencies=[require_internal({"jobs:write"})])
def start_provisioning_job(job_id: int, payload: JobStartPayload, db: Session = Depends(get_db)):
    _ = _require_correlation(payload.correlation_id)
    repo = ProvisioningJobsRepo(db)
    row = repo.get_by_id(int(job_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provisioning job not found")

    current_status = normalize_status(str(getattr(row, "status", "") or ""))
    if current_status in {"RUNNING", "SUCCEEDED", "CANCELLED"}:
        return repo.to_dict(row)

    profile_id = int(getattr(row, "storage_root_access_profile_id", 0) or 0)
    if profile_id > 0:
        profile = db.execute(
            text(
                """
                SELECT id, status, locked_by, locked_at
                FROM storage_root_access_profiles
                WHERE id = :id AND deleted_at IS NULL
                FOR UPDATE
                """
            ),
            {"id": profile_id},
        ).mappings().first()
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root access profile not found")

        now = _utcnow_naive()
        lock_owner = str(payload.lock_owner or f"capsule-job-{int(job_id)}").strip()[:100]
        current_lock_owner = str(profile.get("locked_by") or "").strip()
        locked_at = profile.get("locked_at")
        is_stale = bool(locked_at and isinstance(locked_at, datetime) and locked_at <= (now - timedelta(minutes=10)))
        if (
            str(profile.get("status") or "").upper() == "RUNNING"
            and locked_at
            and not is_stale
            and current_lock_owner
            and current_lock_owner != lock_owner
        ):
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Provisioning lock is active")

        db.execute(
            text(
                """
                UPDATE storage_root_access_profiles
                SET status = 'RUNNING',
                    locked_by = :locked_by,
                    locked_at = :locked_at,
                    capsule_execution_id = :capsule_execution_id,
                    next_retry_at = NULL,
                    error_code = NULL,
                    error_message = NULL,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": profile_id,
                "locked_by": lock_owner,
                "locked_at": now,
                "capsule_execution_id": int(payload.capsule_execution_id or 0) or int(job_id),
                "updated_at": now,
            },
        )

    row = repo.update(
        obj=row,
        updates={
            "status": ensure_transition(current=row.status, next_status="RUNNING"),
            "started_at": row.started_at or _utcnow_naive(),
            "finished_at": None,
            "error_code": None,
            "error_message": None,
        },
    )
    return repo.to_dict(row)


@router.post("/jobs/{job_id}/requeue", dependencies=[require_internal({"jobs:write", "profiles:write"})])
def requeue_provisioning_job(job_id: int, payload: JobRequeuePayload, db: Session = Depends(get_db)):
    _ = _require_correlation(payload.correlation_id)
    repo = ProvisioningJobsRepo(db)
    row = repo.get_by_id(int(job_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provisioning job not found")

    current_status = str(row.status or "").upper()
    if current_status == "RUNNING" and not payload.force:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot requeue RUNNING job without force=true")

    next_status = "QUEUED" if payload.force else ensure_transition(current=current_status, next_status="QUEUED")
    row = repo.update(
        obj=row,
        updates={
            "status": next_status,
            "finished_at": None,
            "error_code": None,
            "error_message": None,
        },
    )

    profile_id = int(getattr(row, "storage_root_access_profile_id", 0) or 0)
    if profile_id > 0:
        db.execute(
            text(
                """
                UPDATE storage_root_access_profiles
                SET status = 'QUEUED',
                    locked_by = NULL,
                    locked_at = NULL,
                    next_retry_at = NULL,
                    capsule_execution_id = NULL,
                    updated_at = :updated_at
                WHERE id = :id AND deleted_at IS NULL
                """
            ),
            {
                "id": profile_id,
                "updated_at": _utcnow_naive(),
            },
        )
        db.commit()

    return repo.to_dict(row)


@router.post("/jobs/{job_id}/cancel", dependencies=[require_internal({"jobs:write", "events:write"})])
def cancel_provisioning_job(job_id: int, payload: JobCancelPayload, db: Session = Depends(get_db)):
    correlation_id = _require_correlation(payload.correlation_id)
    repo = ProvisioningJobsRepo(db)
    row = repo.get_by_id(int(job_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provisioning job not found")

    current_status = normalize_status(str(getattr(row, "status", "") or ""))
    if current_status in {"SUCCEEDED", "FAILED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Terminal job cannot be cancelled")
    if current_status == "CANCELLED":
        return repo.to_dict(row)

    now = _utcnow_naive()
    reason = str(payload.reason or "").strip() or "Cancelled by operator"
    requested_by = str(payload.requested_by or "").strip() or "operator"
    source = str(payload.source or "ui").strip().lower() or "ui"

    metrics = dict(getattr(row, "metrics_json", {}) or {})
    metrics["cancel"] = {
        "requested_at": now.isoformat() + "Z",
        "requested_by": requested_by,
        "source": source,
        "reason": reason,
        "correlation_id": correlation_id,
    }

    row = repo.update(
        obj=row,
        updates={
            "status": ensure_transition(current=row.status, next_status="CANCELLED"),
            "finished_at": now,
            "error_code": "JOB_CANCELLED",
            "error_message": reason,
            "error_json": {
                "code": "JOB_CANCELLED",
                "message": reason,
                "source": source,
                "requested_by": requested_by,
            },
            "metrics_json": metrics,
        },
    )

    if str(getattr(row, "job_type", "") or "").strip().upper() == "DIRECTORY_SNAPSHOT":
        _apply_directory_snapshot_failure(
            db,
            job_row=row,
            error_code="JOB_CANCELLED",
            error_message=reason,
        )

    _persist_identity_source_probe_result(
        db,
        job_type=getattr(row, "job_type", None),
        identity_source_id=getattr(row, "identity_source_id", None),
        result_json=getattr(row, "result_json", None),
        fallback_message=reason,
        status_value="failed",
        job_id=int(getattr(row, "id", 0) or 0) or None,
        correlation_id=correlation_id,
    )

    _write_governance_event(
        db,
        event_type="provisioning_job_cancelled",
        target_type="provisioning_job",
        target_id=int(getattr(row, "id", 0) or 0),
        provisioning_job_id=int(getattr(row, "id", 0) or 0),
        status_value="CANCELLED",
        payload_json={
            "reason": reason,
            "source": source,
            "requested_by": requested_by,
            "correlation_id": correlation_id,
        },
    )
    db.commit()
    return repo.to_dict(row)


@router.post("/jobs/{job_id}/watchdog-republish-mark", dependencies=[require_internal({"jobs:write", "events:write"})])
def mark_watchdog_republish(job_id: int, payload: JobWatchdogRepublishPayload, db: Session = Depends(get_db)):
    correlation_id = _require_correlation(payload.correlation_id)
    repo = ProvisioningJobsRepo(db)
    row = repo.get_by_id(int(job_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provisioning job not found")

    current_status = normalize_status(str(getattr(row, "status", "") or ""))
    if current_status != "QUEUED":
        return repo.to_dict(row)

    metrics = dict(getattr(row, "metrics_json", {}) or {})
    next_count = int(metrics.get("watchdog_republish_count") or 0) + 1
    metrics["watchdog_republish_count"] = next_count
    metrics["last_republish_at"] = _utcnow_naive().isoformat() + "Z"
    metrics["last_republish_reason"] = str(payload.reason or "").strip() or "watchdog"
    metrics["last_republish_correlation_id"] = correlation_id

    row = repo.update(
        obj=row,
        updates={
            "metrics_json": metrics,
            "error_code": None,
            "error_message": None,
        },
    )

    _write_governance_event(
        db,
        event_type="provisioning_job_watchdog_republish",
        target_type="provisioning_job",
        target_id=int(getattr(row, "id", 0) or 0),
        provisioning_job_id=int(getattr(row, "id", 0) or 0),
        status_value="QUEUED",
        payload_json={
            "watchdog_republish_count": next_count,
            "correlation_id": correlation_id,
        },
    )
    db.commit()
    return repo.to_dict(row)


@router.post("/jobs/{job_id}/complete", dependencies=[require_internal({"jobs:write"})])
def complete_provisioning_job(job_id: int, payload: JobCompletePayload, db: Session = Depends(get_db)):
    correlation_id = _require_correlation(payload.correlation_id)
    repo = ProvisioningJobsRepo(db)
    row = repo.get_by_id(int(job_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provisioning job not found")
    if normalize_status(str(getattr(row, "status", "") or "")) == "CANCELLED":
        return repo.to_dict(row)
    row = repo.update(
        obj=row,
        updates={
            "action": payload.action,
            "status": ensure_transition(current=row.status, next_status="SUCCEEDED"),
            "finished_at": _utcnow_naive(),
            "result_json": payload.result_json,
            "metrics_json": payload.metrics_json,
            "error_json": {},
            "error_code": None,
            "error_message": None,
        },
    )

    if str(getattr(row, "job_type", "") or "").strip().upper() == "DIRECTORY_SNAPSHOT":
        _apply_directory_snapshot_success(
            db,
            job_row=row,
            result_json=payload.result_json,
        )
        record_health_event(
            db,
            entity_type="identity_source",
            entity_id=int(getattr(row, "identity_source_id", 0) or 0) or None,
            check_type="snapshot",
            status="success",
            message="Directory snapshot completed",
            source_type="provisioning_job",
            source_id=str(int(getattr(row, "id", 0) or 0)),
            job_id=int(getattr(row, "id", 0) or 0) or None,
            correlation_id=correlation_id,
            checked_at=_utcnow_naive(),
            metadata_json={
                "job_type": "DIRECTORY_SNAPSHOT",
                "result": payload.result_json or {},
            },
        )

    _persist_identity_source_probe_result(
        db,
        job_type=getattr(row, "job_type", None),
        identity_source_id=getattr(row, "identity_source_id", None),
        result_json=payload.result_json,
        status_value="success",
        job_id=int(getattr(row, "id", 0) or 0) or None,
        correlation_id=correlation_id,
    )
    _persist_storage_endpoint_probe_result(
        db,
        job_row=row,
        result_json=payload.result_json,
        status_value="success",
        correlation_id=correlation_id,
    )
    _persist_storage_root_probe_result(
        db,
        job_row=row,
        result_json=payload.result_json,
        status_value="success",
        correlation_id=correlation_id,
    )

    _write_governance_event(
        db,
        event_type="provisioning_job_succeeded",
        target_type="provisioning_job",
        target_id=int(getattr(row, "id", 0) or 0),
        provisioning_job_id=int(getattr(row, "id", 0) or 0),
        storage_root_access_profile_id=int(getattr(row, "storage_root_access_profile_id", 0) or 0) or None,
        status_value="SUCCEEDED",
        payload_json={
            "correlation_id": correlation_id,
            "action": payload.action or getattr(row, "action", None),
            "result_json": payload.result_json or {},
            "metrics_json": payload.metrics_json or {},
        },
        actor_ip=payload.actor_ip,
        user_agent=payload.user_agent,
    )
    db.commit()
    return repo.to_dict(row)


@router.post("/jobs/{job_id}/fail", dependencies=[require_internal({"jobs:write"})])
def fail_provisioning_job(job_id: int, payload: JobFailPayload, db: Session = Depends(get_db)):
    correlation_id = _require_correlation(payload.correlation_id)
    repo = ProvisioningJobsRepo(db)
    row = repo.get_by_id(int(job_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provisioning job not found")
    if normalize_status(str(getattr(row, "status", "") or "")) == "CANCELLED":
        return repo.to_dict(row)
    if not str(payload.error_code or "").strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="error_code is required")
    row = repo.update(
        obj=row,
        updates={
            "action": payload.action,
            "status": ensure_transition(current=row.status, next_status="FAILED"),
            "finished_at": _utcnow_naive(),
            "result_json": payload.result_json,
            "metrics_json": payload.metrics_json,
            "error_json": payload.error_json
            or {
                "code": payload.error_code,
                "message": payload.error_message,
            },
            "error_code": payload.error_code,
            "error_message": payload.error_message,
        },
    )

    if str(getattr(row, "job_type", "") or "").strip().upper() == "DIRECTORY_SNAPSHOT":
        _apply_directory_snapshot_failure(
            db,
            job_row=row,
            error_code=payload.error_code,
            error_message=payload.error_message,
        )
        record_health_event(
            db,
            entity_type="identity_source",
            entity_id=int(getattr(row, "identity_source_id", 0) or 0) or None,
            check_type="snapshot",
            status="failed",
            message=payload.error_message,
            source_type="provisioning_job",
            source_id=str(int(getattr(row, "id", 0) or 0)),
            job_id=int(getattr(row, "id", 0) or 0) or None,
            correlation_id=correlation_id,
            checked_at=_utcnow_naive(),
            metadata_json={
                "job_type": "DIRECTORY_SNAPSHOT",
                "error_code": payload.error_code,
                "error": payload.error_json or {},
            },
        )

    _persist_identity_source_probe_result(
        db,
        job_type=getattr(row, "job_type", None),
        identity_source_id=getattr(row, "identity_source_id", None),
        result_json=payload.result_json,
        fallback_message=payload.error_message,
        status_value="failed",
        job_id=int(getattr(row, "id", 0) or 0) or None,
        correlation_id=correlation_id,
    )
    _persist_storage_endpoint_probe_result(
        db,
        job_row=row,
        result_json=payload.result_json,
        fallback_message=payload.error_message,
        status_value="failed",
        correlation_id=correlation_id,
    )
    _persist_storage_root_probe_result(
        db,
        job_row=row,
        result_json=payload.result_json,
        fallback_message=payload.error_message,
        status_value="failed",
        correlation_id=correlation_id,
    )

    _write_governance_event(
        db,
        event_type="provisioning_job_failed",
        target_type="provisioning_job",
        target_id=int(getattr(row, "id", 0) or 0),
        provisioning_job_id=int(getattr(row, "id", 0) or 0),
        storage_root_access_profile_id=int(getattr(row, "storage_root_access_profile_id", 0) or 0) or None,
        status_value="FAILED",
        payload_json={
            "correlation_id": correlation_id,
            "action": payload.action or getattr(row, "action", None),
            "error_code": payload.error_code,
            "error_message": payload.error_message,
            "error_json": payload.error_json
            or {
                "code": payload.error_code,
                "message": payload.error_message,
            },
            "metrics_json": payload.metrics_json or {},
        },
        actor_ip=payload.actor_ip,
        user_agent=payload.user_agent,
    )
    db.commit()
    return repo.to_dict(row)


@router.post("/jobs/{job_id}/complete-and-apply", dependencies=[require_internal({"jobs:write", "events:write"})])
def complete_and_apply_provisioning(job_id: int, payload: CompleteAndApplyPayload, db: Session = Depends(get_db)):
    _ = _require_correlation(payload.correlation_id)
    now = _utcnow_naive()
    outcome = normalize_status(payload.outcome)
    if outcome not in {"SUCCEEDED", "FAILED"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="outcome must be SUCCEEDED or FAILED")
    if outcome == "FAILED" and not str(payload.error_code or "").strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="error_code is required when outcome=FAILED")
    if outcome == "SUCCEEDED" and not str(payload.group_external_id or "").strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="group_external_id is required when outcome=SUCCEEDED")

    idem_row = db.execute(
        text(
            """
            SELECT id
            FROM governance_events
            WHERE provisioning_job_id = :job_id
              AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.correlation_id')) = :correlation_id
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {
            "job_id": int(job_id),
            "correlation_id": payload.correlation_id,
        },
    ).mappings().first()
    if idem_row:
        repo = ProvisioningJobsRepo(db)
        existing = repo.get_by_id(int(job_id))
        return repo.to_dict(existing) if existing else {"id": int(job_id)}

    job_row = db.execute(
        text(
            """
            SELECT id, status, storage_root_access_profile_id
            FROM provisioning_jobs
            WHERE id = :id
            LIMIT 1
            """
        ),
        {"id": int(job_id)},
    ).mappings().first()
    if not job_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provisioning job not found")

    profile_row = db.execute(
        text(
            """
            SELECT id, status, group_external_id, attempt_count
            FROM storage_root_access_profiles
            WHERE id = :id AND deleted_at IS NULL
            LIMIT 1
            """
        ),
        {"id": int(payload.profile_id)},
    ).mappings().first()
    if not profile_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storage root access profile not found")

    job_next = ensure_transition(current=str(job_row.get("status") or "QUEUED"), next_status=outcome)
    profile_next = ensure_transition(current=str(profile_row.get("status") or "QUEUED"), next_status=outcome)

    retry_next_at: datetime | None = None
    next_attempt_count = int(profile_row.get("attempt_count") or 0)
    job_attempt_count = int((payload.metrics_json or {}).get("retries") or 0)
    if outcome == "FAILED":
        next_attempt_count = _next_retry_attempt_count(job_attempt_count, next_attempt_count)
        if next_attempt_count < MAX_RETRY_ATTEMPTS:
            profile_next = "RETRYING"
            retry_next_at = now + timedelta(minutes=_retry_backoff_minutes(next_attempt_count))

    validate_profile_invariants(
        status_value=profile_next,
        group_external_id=payload.group_external_id if profile_next == "SUCCEEDED" else profile_row.get("group_external_id"),
        error_code=payload.error_code if profile_next == "FAILED" else None,
    )

    db.execute(
        text(
            """
            UPDATE provisioning_jobs
            SET status = :status,
                action = :action,
                result_json = :result_json,
                metrics_json = :metrics_json,
                error_json = :error_json,
                error_code = :error_code,
                error_message = :error_message,
                finished_at = :finished_at,
                updated_at = :updated_at
            WHERE id = :id
            """
        ),
        {
            "id": int(job_id),
            "status": job_next,
            "action": payload.action,
            "result_json": json.dumps(payload.result_json or {}, ensure_ascii=False),
            "metrics_json": json.dumps(payload.metrics_json or {}, ensure_ascii=False),
            "error_json": json.dumps(
                payload.error_json
                or (
                    {"code": payload.error_code, "message": payload.error_message}
                    if outcome == "FAILED"
                    else {}
                ),
                ensure_ascii=False,
            ),
            "error_code": payload.error_code if outcome == "FAILED" else None,
            "error_message": payload.error_message if outcome == "FAILED" else None,
            "finished_at": now,
            "updated_at": now,
        },
    )

    db.execute(
        text(
            """
            UPDATE storage_root_access_profiles
            SET status = :status,
                group_external_id = :group_external_id,
                attempt_count = :attempt_count,
                locked_by = NULL,
                locked_at = NULL,
                capsule_execution_id = NULL,
                next_retry_at = :next_retry_at,
                error_code = :error_code,
                error_message = :error_message,
                updated_at = :updated_at
            WHERE id = :id
            """
        ),
        {
                "id": int(payload.profile_id),
                "status": profile_next,
                "group_external_id": payload.group_external_id if profile_next == "SUCCEEDED" else profile_row.get("group_external_id"),
                "attempt_count": next_attempt_count,
                "next_retry_at": retry_next_at,
                "error_code": payload.error_code if outcome == "FAILED" else None,
                "error_message": payload.error_message if outcome == "FAILED" else None,
                "updated_at": now,
            },
        )

    _write_governance_event(
        db,
        event_type=payload.event_type,
        target_type="storage_root_access_profile",
        target_id=int(payload.profile_id),
        storage_root_access_profile_id=int(payload.profile_id),
        provisioning_job_id=int(job_id),
        status_value=profile_next,
        payload_json={
            **(payload.event_payload_json or {}),
            "correlation_id": payload.correlation_id,
            "result_json": payload.result_json,
            "error_code": payload.error_code,
            "error_message": payload.error_message,
        },
        actor_ip=payload.actor_ip,
        user_agent=payload.user_agent,
    )
    db.commit()

    repo = ProvisioningJobsRepo(db)
    updated = repo.get_by_id(int(job_id))
    out = repo.to_dict(updated) if updated else {"id": int(job_id), "status": job_next}
    out["profile_status"] = profile_next
    out["attempt_count"] = next_attempt_count
    out["next_retry_at"] = retry_next_at
    return out


@router.get("/reconcile-candidates", dependencies=[require_internal({"jobs:read", "profiles:write"})])
def list_reconcile_candidates(limit: int = 200, db: Session = Depends(get_db)):
    lim = max(1, min(int(limit), 1000))
    rows = db.execute(
        text(
            """
            SELECT
              srap.id AS storage_root_access_profile_id,
              srap.storage_root_id,
              srap.status,
              srap.attempt_count,
              srap.locked_at,
              srap.next_retry_at,
              (
                SELECT pj.id
                FROM provisioning_jobs pj
                WHERE pj.storage_root_access_profile_id = srap.id
                ORDER BY pj.id DESC
                LIMIT 1
              ) AS job_id
            FROM storage_root_access_profiles srap
            WHERE srap.deleted_at IS NULL
              AND (
                (
                  UPPER(COALESCE(srap.status, '')) = 'RUNNING'
                  AND srap.locked_at IS NOT NULL
                  AND srap.locked_at <= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 10 MINUTE)
                )
                OR (
                  UPPER(COALESCE(srap.status, '')) = 'RETRYING'
                  AND srap.next_retry_at IS NOT NULL
                  AND srap.next_retry_at <= UTC_TIMESTAMP()
                )
              )
            ORDER BY srap.id ASC
            LIMIT :lim
            """
        ),
        {"lim": lim},
    ).mappings().all()

    out: list[dict] = []
    for row in rows:
        job_id = int(row.get("job_id") or 0)
        if job_id <= 0:
            continue
        out.append(
            {
                "storage_root_access_profile_id": int(row.get("storage_root_access_profile_id") or 0),
                "storage_root_id": int(row.get("storage_root_id") or 0),
                "status": str(row.get("status") or "").upper(),
                "attempt_count": int(row.get("attempt_count") or 0),
                "locked_at": row.get("locked_at"),
                "next_retry_at": row.get("next_retry_at"),
                "job_id": job_id,
            }
        )
    return out
