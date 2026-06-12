from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.core.settings import get_settings

settings = get_settings()
logger = get_logger("governance.audit")

ALLOWED_RESULTS = {"success", "failure", "denied", "in_progress"}
ALLOWED_SEVERITIES = {"info", "warning", "error", "critical"}
ALLOWED_SCOPES = {"business", "technical"}


def _as_actor_id(actor_id: Any) -> str:
    value = "" if actor_id is None else str(actor_id).strip()
    return value or "system"


def _normalize_result(value: str | None) -> str:
    raw = str(value or "success").strip().lower()
    return raw if raw in ALLOWED_RESULTS else "success"


def _normalize_severity(value: str | None) -> str:
    raw = str(value or "info").strip().lower()
    return raw if raw in ALLOWED_SEVERITIES else "info"


def _normalize_scope(value: str | None) -> str:
    raw = str(value or "business").strip().lower()
    return raw if raw in ALLOWED_SCOPES else "business"


def _sanitize_metadata(value: dict[str, Any] | None) -> dict[str, Any]:
    src = value or {}
    if not isinstance(src, dict):
        src = {"details": str(src)}

    if any(k in src for k in ("before", "after", "details")):
        normalized = {
            "before": src.get("before"),
            "after": src.get("after"),
            "details": src.get("details"),
        }
    else:
        normalized = {
            "before": None,
            "after": None,
            "details": src,
        }

    def _scrub(obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                lk = str(k).lower()
                if any(s in lk for s in ("password", "token", "secret", "stack", "traceback")):
                    continue
                out[k] = _scrub(v)
            return out
        if isinstance(obj, list):
            return [_scrub(x) for x in obj]
        return obj

    cleaned = _scrub(normalized)
    if not isinstance(cleaned, dict):
        return {"before": None, "after": None, "details": None}
    return {
        "before": cleaned.get("before"),
        "after": cleaned.get("after"),
        "details": cleaned.get("details"),
    }


def log_event(
    *,
    action: str,
    event_category: str,
    actor_type: str,
    actor_id: Any,
    entity_type: str,
    entity_id: Any = None,
    zone_id: int | None = None,
    storage_root_id: int | None = None,
    correlation_id: str | None = None,
    result: str = "success",
    severity: str = "info",
    metadata_json: dict[str, Any] | None = None,
    event_scope: str = "business",
    actor_ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Best-effort business audit emission (never blocking, never raising).

    Wizard-UI runtime bridge is intentionally disabled.
    Governance accepts audit intents but does not forward them to wizard-ui.
    """

    if not getattr(settings, "wizard_activity_enabled", True):
        return

    payload = {
        "action": str(action or "").strip() or "unknown_action",
        "event_category": str(event_category or "").strip() or "PROVISIONING",
        "event_scope": _normalize_scope(event_scope),
        "actor_type": str(actor_type or "system").strip().lower() or "system",
        "actor_id": _as_actor_id(actor_id),
        "entity_type": str(entity_type or "request").strip() or "request",
        "entity_id": None if entity_id is None else str(entity_id),
        "zone_id": zone_id,
        "storage_root_id": storage_root_id,
        "correlation_id": str(correlation_id or "").strip() or None,
        "result": _normalize_result(result),
        "severity": _normalize_severity(severity),
        "metadata_json": _sanitize_metadata(metadata_json),
        "actor_ip": actor_ip,
        "user_agent": user_agent,
    }

    # Forward to DAL /activity/events (best-effort, never blocking)
    try:
        import httpx  # lazy import
        from app.core.internal_auth import build_internal_headers

        # DAL app routers are mounted under API prefix (/api)
        url = settings.dal_url.rstrip("/") + "/api/activity/events"
        headers = build_internal_headers()
        headers["X-Service-Name"] = "governance"
        headers["X-Service-Scope"] = "events:write"

        # Map governance payload → DAL activity write model
        dal_payload = {
            "action": payload.get("action"),
            "actor_type": payload.get("actor_type"),
            "actor_id": payload.get("actor_id"),
            "entity_type": payload.get("entity_type"),
            "entity_id": payload.get("entity_id"),
            "zone_id": payload.get("zone_id"),
            "root_id": payload.get("storage_root_id"),
            "result": payload.get("result"),
            "severity": payload.get("severity"),
            "correlation_id": payload.get("correlation_id"),
            "source_service": "governance",
            "metadata_json": payload.get("metadata_json"),
        }

        with httpx.Client(timeout=int(getattr(settings, "wizard_activity_timeout_seconds", 5) or 5)) as client:
            r = client.post(url, json=dal_payload, headers=headers)
            # Never block business flow
            if r.status_code >= 400:
                logger.debug("audit forward failed", extra={"status": r.status_code})
    except Exception as exc:
        logger.debug("audit forward exception", exc_info=exc)

    # Always keep a local debug trace (useful when DAL is down)
    logger.debug("audit event accepted", extra={"action": payload.get("action"), "entity_type": payload.get("entity_type")})
