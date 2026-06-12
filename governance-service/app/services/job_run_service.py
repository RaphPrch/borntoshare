from __future__ import annotations

from typing import Any


API_JOB_STATUS = {
    "queued",
    "running",
    "retrying",
    "succeeded",
    "failed",
    "partial",
    "cancelled",
    "timed_out",
}


def normalize_job_status(raw: str | None) -> str:
    value = str(raw or "").strip().upper()
    aliases = {
        "": "queued",
        "PENDING": "queued",
        "QUEUE": "queued",
        "CREATED": "queued",
        "QUEUED": "queued",
        "RUNNING": "running",
        "RETRYING": "retrying",
        "DONE": "succeeded",
        "SUCCESS": "succeeded",
        "SUCCEEDED": "succeeded",
        "FAILED": "failed",
        "ERROR": "failed",
        "PARTIAL": "partial",
        "CANCELLED": "cancelled",
        "TIMED_OUT": "timed_out",
        "TIMEOUT": "timed_out",
    }
    status = aliases.get(value, value.lower())
    return status if status in API_JOB_STATUS else "queued"


def build_job_run_data(job_id: int | str, row: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(row or {})
    result = data.get("result_json") if isinstance(data.get("result_json"), dict) else {}
    metrics = data.get("metrics_json") if isinstance(data.get("metrics_json"), dict) else {}
    error = data.get("error_json") if isinstance(data.get("error_json"), dict) else {}

    if not error and data.get("error_code"):
        error = {
            "code": data.get("error_code"),
            "message": data.get("error_message"),
        }

    return {
        "job_id": str(job_id),
        "run_id": str(job_id),
        "job_type": data.get("job_type"),
        "action": data.get("action"),
        "status": normalize_job_status(data.get("status")),
        "correlation_id": data.get("correlation_id"),
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
        "result": result,
        "metrics": metrics,
        "error": error,
    }

