from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.inspection import inspect as sa_inspect

from app.models.provisioning_job import ProvisioningJob
from app.utils.status_validation import (
    ensure_transition,
    normalize_status,
    validate_job_invariants,
)


class ProvisioningJobsRepo:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, data: dict) -> ProvisioningJob:
        payload = dict(data)
        payload["status"] = normalize_status(payload.get("status") or "QUEUED")
        if payload.get("error_json") is None:
            payload["error_json"] = {}
        if payload.get("metrics_json") is None:
            payload["metrics_json"] = {}
        validate_job_invariants(
            status_value=payload.get("status"),
            finished_at=payload.get("finished_at"),
            error_code=payload.get("error_code"),
        )
        obj = ProvisioningJob(**payload)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def get_by_id(self, job_id: int) -> ProvisioningJob | None:
        return self.db.get(ProvisioningJob, int(job_id))

    def get_by_correlation(self, correlation_id: str) -> ProvisioningJob | None:
        return (
            self.db.query(ProvisioningJob)
            .filter(ProvisioningJob.correlation_id == str(correlation_id))
            .first()
        )

    def get_latest_by_profile(self, profile_id: int) -> ProvisioningJob | None:
        return (
            self.db.query(ProvisioningJob)
            .filter(ProvisioningJob.storage_root_access_profile_id == int(profile_id))
            .order_by(ProvisioningJob.id.desc())
            .first()
        )

    def update(self, *, obj: ProvisioningJob, updates: dict) -> ProvisioningJob:
        payload = dict(updates)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if "status" in payload:
            payload["status"] = ensure_transition(current=obj.status, next_status=payload.get("status"))

        next_status = str(payload.get("status") or obj.status or "QUEUED").upper()
        if next_status == "RUNNING" and payload.get("started_at") is None and obj.started_at is None:
            payload["started_at"] = now
        if next_status in {"SUCCEEDED", "FAILED"} and payload.get("finished_at") is None:
            payload["finished_at"] = now

        validate_job_invariants(
            status_value=payload.get("status") or obj.status,
            finished_at=payload.get("finished_at") or obj.finished_at,
            error_code=payload.get("error_code") if "error_code" in payload else obj.error_code,
        )

        if "error_json" in payload and payload.get("error_json") is None:
            payload["error_json"] = {}
        if "metrics_json" in payload and payload.get("metrics_json") is None:
            payload["metrics_json"] = {}

        for field, value in payload.items():
            setattr(obj, field, value)

        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    @staticmethod
    def to_dict(obj: ProvisioningJob) -> dict:
        mapper = sa_inspect(obj.__class__)
        return {col.key: getattr(obj, col.key) for col in mapper.columns}
