from __future__ import annotations

import contextvars
import logging

from app.core.config import get_settings


_DEFAULT_SERVICE = "dal-service"
_REQUEST_ID_CTX: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "dal_request_id",
    default=None,
)


def init_logging() -> logging.Logger:
    settings = get_settings()

    # ---------------------------------------------------------
    # Log level
    # ---------------------------------------------------------
    level_name = settings.LOG_LEVEL.upper()
    level = getattr(logging, level_name, logging.INFO)

    # ---------------------------------------------------------
    # DAL logger only (no root hijacking)
    # ---------------------------------------------------------
    logger = logging.getLogger("dal")
    logger.setLevel(level)

    handler = logging.StreamHandler()
    handler.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [DAL] %(name)s - %(message)s"
    )
    handler.setFormatter(formatter)

    # Avoid duplicate handlers (important in reload / tests)
    if not logger.handlers:
        logger.addHandler(handler)

    logger.propagate = False

    # ---------------------------------------------------------
    # SQLAlchemy tuning
    # ---------------------------------------------------------
    if settings.APP_ENV == "dev":
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
        logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    else:
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    logger.info(
        "DAL logger initialized | env=%s | level=%s",
        settings.APP_ENV,
        settings.LOG_LEVEL,
    )

    return logger


def get_logger(name: str) -> logging.Logger:
    # Keep this helper side-effect free at import time.
    # App bootstrap is responsible for calling init_logging().
    if str(name).startswith("dal"):
        return logging.getLogger(name)
    return logging.getLogger(f"dal.{name}")


def set_request_id_context(request_id: str | None) -> None:
    value = str(request_id or "").strip() or None
    _REQUEST_ID_CTX.set(value)


def get_request_id_context() -> str | None:
    return _REQUEST_ID_CTX.get()


def clear_request_id_context() -> None:
    _REQUEST_ID_CTX.set(None)


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
        rid = get_request_id_context()
        if rid:
            enriched["request_id"] = rid

    ordered_first = [
        "service",
        "module",
        "action",
        "request_id",
        "user_id",
        "actor_id",
        "zone_id",
        "storage_root_id",
        "identity_source_id",
        "target",
        "outcome",
        "status_code",
        "error_code",
    ]
    keys: list[str] = []
    for key in ordered_first:
        if key in enriched:
            keys.append(key)
    keys.extend([key for key in enriched if key not in keys])

    parts: list[str] = []
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
