from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.core.action_registry import CapsuleActionError, execute_action
from app.core.scope_guard import ensure_action_scope_allowed
from app.services.dal_client import dal_get, dal_post
from app.shared.b2s_job_contracts.contracts import default_action_for_job_type


logger = logging.getLogger("capsule-runner.dispatcher")


def _normalize_status(value: Optional[str]) -> str:
    return str(value or "").strip().upper()


def _extract_payload(job: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    payload_json = dict(job.get("payload_json") or {})

    action = str(job.get("action") or payload_json.get("action") or "").strip()
    payload = payload_json.get("payload") if isinstance(payload_json.get("payload"), dict) else None

    if payload is None:
        payload = {}

    if not action:
        try:
            action = default_action_for_job_type(str(job.get("job_type") or ""))
        except ValueError as exc:
            raise CapsuleActionError(
                error_code="CAPSULE_UNSUPPORTED_JOB_TYPE",
                message=str(exc),
                retryable=False,
            ) from exc

    payload.setdefault("job_id", int(job.get("id") or 0) or None)
    return action, payload


def _build_metrics(result: dict[str, Any] | None, retries: int, max_retries: int) -> dict[str, Any]:
    base = dict((result or {}).get("metrics") or {})
    base.setdefault("retries", int(retries))
    base.setdefault("max_retries", int(max_retries))
    return base


def run_job(job_id: int, *, retries: int = 0, max_retries: int = 5) -> None:
    numeric_job_id = int(job_id)
    job = dal_get(f"/api/internal/provisioning/jobs/{numeric_job_id}")
    if not isinstance(job, dict):
        raise RuntimeError("job not found")

    status = _normalize_status(job.get("status"))
    correlation_id = str(job.get("correlation_id") or "").strip() or None
    if status in {"SUCCEEDED", "FAILED"}:
        logger.info("dispatcher.skip_terminal", extra={"job_id": numeric_job_id, "status": status})
        return

    if status in {"CREATED", "QUEUED", "RETRYING"}:
        dal_post(
            f"/api/internal/provisioning/jobs/{numeric_job_id}/start",
            {
                "correlation_id": correlation_id or f"job_{numeric_job_id}",
                "lock_owner": f"capsule-job-{numeric_job_id}",
                "capsule_execution_id": numeric_job_id,
            },
        )

    action = "unknown"
    final_error_code = "CAPSULE_EXECUTION_FAILED"
    final_error_message = "Execution failed"
    final_result_json: dict[str, Any] = {}

    try:
        action, action_payload = _extract_payload(job)
        ensure_action_scope_allowed(action)
        result_payload = execute_action(action, action_payload, job_id=numeric_job_id)
        metrics = _build_metrics(result_payload, retries, max_retries)
        complete_payload = {
            "action": action,
            "result_json": result_payload,
            "metrics_json": metrics,
            "correlation_id": correlation_id or f"job_{numeric_job_id}",
        }

        dal_post(
            f"/api/internal/provisioning/jobs/{numeric_job_id}/complete",
            complete_payload,
        )
        return
    except Exception as exc:
        if isinstance(exc, CapsuleActionError):
            final_error_code = exc.error_code
            final_error_message = str(exc.message)[:2000]
            retryable = bool(exc.retryable)
            final_result_json = {
                "success": False,
                "message": final_error_message,
                "details": dict(exc.details or {}),
            }
        elif isinstance(exc, httpx.HTTPStatusError):
            status_code = int(getattr(exc.response, "status_code", 0) or 0)
            final_error_code = f"CAPSULE_DAL_HTTP_{status_code}" if status_code > 0 else "CAPSULE_DAL_HTTP_ERROR"

            response_detail = ""
            try:
                response_detail = str(getattr(exc.response, "text", "") or "").strip()
            except Exception:
                response_detail = ""

            msg = str(exc)
            if response_detail:
                msg = f"{msg} | response={response_detail[:1200]}"
            final_error_message = msg[:2000]

            # 4xx means contract/payload issue (non-transient), 5xx/408/429 may be transient.
            retryable = status_code in {408, 425, 429} or status_code >= 500 or status_code <= 0
        else:
            final_error_code = "CAPSULE_EXECUTION_FAILED"
            final_error_message = str(exc)[:2000]
            retryable = True

        is_final_attempt = retries >= max_retries
        if not retryable:
            is_final_attempt = True
        if not is_final_attempt:
            raise

        error_payload = {
            "code": final_error_code,
            "message": final_error_message,
            "retryable": retryable,
        }

        dal_post(
            f"/api/internal/provisioning/jobs/{numeric_job_id}/fail",
            {
                "action": action,
                "error_code": final_error_code,
                "error_message": final_error_message,
                "result_json": final_result_json,
                "metrics_json": {"retries": retries, "max_retries": max_retries},
                "error_json": error_payload,
                "correlation_id": correlation_id or f"job_{numeric_job_id}",
            },
        )
