from __future__ import annotations

import contextvars
import logging
from typing import Final

from app.core.config import get_settings

# -----------------------------------------------------------
# Log level normalization
# -----------------------------------------------------------

_LEVEL_MAP: Final[dict[str, str]] = {
    "ERR": "ERROR",
    "ERROR": "ERROR",
    "WARN": "WARNING",
    "WARNING": "WARNING",
    "INFO": "INFO",
    "DEBUG": "DEBUG",
    "TRACE": "DEBUG",
}

_DEFAULT_SERVICE: Final[str] = "auth-service"
_REQUEST_ID_CTX: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "auth_request_id",
    default=None,
)


def _normalize_level(raw_level: str) -> str:
    value = (raw_level or "INFO").upper()
    return _LEVEL_MAP.get(value, value)


# -----------------------------------------------------------
# Logging setup (call once at startup)
# -----------------------------------------------------------

def setup_logging() -> None:
    """
    Configure global logging.

    RULES (V1):
    - LOG_LEVEL is the primary source of truth
    """
    settings = get_settings()

    raw_level = settings.LOG_LEVEL
    level_name = _normalize_level(raw_level)

    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [AUTH] [%(levelname)s] %(name)s - %(message)s",
    )

    # Make sure uvicorn loggers inherit our level
    logging.getLogger("uvicorn").setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)


# -----------------------------------------------------------
# Logger factory
# -----------------------------------------------------------

def get_logger(name: str) -> logging.Logger:
    """
    Return a namespaced logger.

    NOTE:
    - setup_logging() MUST be called once at application startup
    """
    return logging.getLogger(name)


def set_request_id_context(request_id: str | None) -> None:
    value = str(request_id or "").strip() or None
    _REQUEST_ID_CTX.set(value)


def get_request_id_context() -> str | None:
    return _REQUEST_ID_CTX.get()


def clear_request_id_context() -> None:
    _REQUEST_ID_CTX.set(None)


def mask_session_id(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return "-"
    if len(raw) <= 8:
        return f"{raw[:2]}***"
    return f"{raw[:4]}...{raw[-4:]}"


def log_event(
    logger: logging.Logger,
    level: int,
    event_name: str,
    **fields: object,
) -> None:
    enriched: dict[str, object] = dict(fields)

    if "service" not in enriched:
        enriched["service"] = _DEFAULT_SERVICE
    if "module" not in enriched:
        enriched["module"] = logger.name
    if "action" not in enriched:
        enriched["action"] = event_name.lower()

    if not enriched.get("request_id"):
        request_id = get_request_id_context()
        if request_id:
            enriched["request_id"] = request_id

    parts: list[str] = []
    ordered_first = [
        "service",
        "module",
        "action",
        "request_id",
        "user_id",
        "actor",
        "provider",
        "target",
        "outcome",
        "status_code",
        "error_code",
    ]
    keys: list[str] = []
    for key in ordered_first:
        if key in enriched:
            keys.append(key)
    keys.extend([k for k in enriched.keys() if k not in keys])

    for key in keys:
        value = enriched[key]
        if value is None:
            continue
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = str(value)
        parts.append(f"{key}={rendered}")

    suffix = f" | {' '.join(parts)}" if parts else ""
    logger.log(level, f"{event_name}{suffix}")
