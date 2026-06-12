from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from app.core.dal_client import dal_post
from app.shared.b2s_job_contracts.actors import publish_job
from app.shared.b2s_job_contracts.contracts import contract_for_job_type


def _normalize_job_status(raw: str | None) -> str:
    value = str(raw or "").strip().upper()
    aliases = {
        "PENDING": "QUEUED",
        "QUEUE": "QUEUED",
        "SUCCESS": "SUCCEEDED",
        "DONE": "SUCCEEDED",
        "OK": "SUCCEEDED",
        "ERROR": "FAILED",
    }
    normalized = aliases.get(value, value)
    if normalized not in {"QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "RETRYING", "CREATED"}:
        return "QUEUED"
    return normalized


def _normalize_create_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(raw or {})
    job_type = str(payload.get("job_type") or "").strip().upper()
    try:
        job_contract = contract_for_job_type(job_type)
    except ValueError as exc:
        raise ValueError("GOVERNANCE_JOB_TYPE_UNSUPPORTED") from exc

    status = _normalize_job_status(payload.get("status") or "QUEUED")

    raw_payload_json = payload.get("payload_json") if isinstance(payload.get("payload_json"), dict) else {}
    if not isinstance(raw_payload_json.get("payload"), dict):
        raise ValueError("GOVERNANCE_JOB_PAYLOAD_ENVELOPE_REQUIRED")
    job_payload = dict(raw_payload_json)

    action = str(payload.get("action") or "").strip()
    if not action:
        nested_payload = job_payload.get("payload") if isinstance(job_payload.get("payload"), dict) else {}
        template = nested_payload.get("template") if isinstance(nested_payload.get("template"), dict) else {}
        action = str(template.get("slug") or "").strip()
    if not action:
        action = str(job_payload.get("action") or "").strip()
    if not action:
        action = job_contract.default_action

    if isinstance(job_payload.get("payload"), dict):
        payload_section = dict(job_payload.get("payload") or {})
        payload_section.setdefault("template", {"slug": action, "version": "v1"})
        job_payload["payload"] = payload_section
    job_payload["action"] = action or None

    metrics_json = payload.get("metrics_json") if isinstance(payload.get("metrics_json"), dict) else {}
    metrics_json = dict(metrics_json)
    metrics_json.setdefault("submitted_by", "governance")
    metrics_json.setdefault("dispatch_policy", "idempotent_recover")
    metrics_json.setdefault("job_type", job_type or "AD_GROUP_ENSURE")
    if action:
        metrics_json.setdefault("action", action)

    return {
        "correlation_id": payload.get("correlation_id"),
        "job_type": job_type or "AD_GROUP_ENSURE",
        "action": action or None,
        "status": status,
        "storage_root_access_profile_id": payload.get("storage_root_access_profile_id"),
        "identity_source_id": payload.get("identity_source_id"),
        "payload_json": job_payload,
        "result_json": payload.get("result_json") if isinstance(payload.get("result_json"), dict) else {},
        "metrics_json": metrics_json,
        "error_json": payload.get("error_json") if isinstance(payload.get("error_json"), dict) else {},
        "error_code": payload.get("error_code"),
        "error_message": payload.get("error_message"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
    }


async def create_and_publish_job(
    *,
    payload: Dict[str, Any],
    dal_post_fn: Optional[Callable[[str, Dict[str, Any], int], Awaitable[Any]]] = None,
    actor: Optional[Any] = None,
) -> Dict[str, Any]:
    post_fn = dal_post_fn or dal_post
    try:
        create_payload = _normalize_create_payload(payload)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    create_job = await post_fn("/api/internal/provisioning/jobs", create_payload, 8)
    job = (create_job or {}).get("data") or {}
    created = bool((create_job or {}).get("created"))
    job_id = int(job.get("id") or 0)
    if job_id <= 0:
        raise RuntimeError("GOVERNANCE_JOB_SUBMIT_FAILED")

    # Idempotence + resiliency:
    # - created=True  -> always dispatch to queue
    # - created=False -> dispatch only if existing job is still dispatchable
    #                  (recovery when initial publish failed after DAL create)
    existing_status = _normalize_job_status(job.get("status"))
    should_dispatch_existing = existing_status in {"CREATED", "QUEUED", "RETRYING"}
    should_dispatch = created or should_dispatch_existing

    if should_dispatch:
        if actor is not None and hasattr(actor, "send"):
            actor.send(job_id)
        else:
            publish_job(str(create_payload.get("job_type") or ""), job_id)

    return {"job_id": job_id, "job": job}
