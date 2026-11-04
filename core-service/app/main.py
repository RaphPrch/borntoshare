from __future__ import annotations

import hmac
import os

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.core.config import get_settings
from app.core.db import SessionLocal, ensure_schema_contract_checked
from app.core.errors import ensure_request_id, json_error_response, register_exception_handlers
from app.core.logging import (
    get_logger,
    get_request_id_context,
    init_logging,
    set_request_id_context,
)
from app.api.internal_auth_local import router as internal_auth_local_router
from app.api import router as api_router
from app.api.governance import router as governance_router
from app.jobs.watchdog import start_jobs_watchdog
from app.jobs.infra_scheduler import start_infra_scheduler
from app.data.repositories.access_requests_views_repo import AccessRequestsReadModelContractError

settings = get_settings()
init_logging()
logger = get_logger("core-app")


# ============================================================
# Application
# ============================================================

def _check_schema_contract() -> None:
    db = SessionLocal()
    try:
        ensure_schema_contract_checked(bind=db.get_bind())
    finally:
        db.close()


def _apply_log_level() -> None:
    """Log level chosen in Advanced Settings › Logging (LOG_LEVEL until it is set)."""
    from app.services.log_retention import apply_log_level, logging_settings

    db = SessionLocal()
    try:
        apply_log_level(logging_settings(db)["level"])
    except Exception:
        pass  # settings table not migrated yet: LOG_LEVEL stays
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup checks, then the two background loops (jobs watchdog, infrastructure schedules), stopped on shutdown."""
    _check_schema_contract()
    _apply_log_level()
    tasks = [task for task in (start_jobs_watchdog(), start_infra_scheduler()) if task is not None]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(**settings.fastapi_kwargs(), lifespan=lifespan)


@app.exception_handler(AccessRequestsReadModelContractError)
async def _access_requests_read_model_contract_handler(request: Request, exc: AccessRequestsReadModelContractError):
    request_id = ensure_request_id(request)
    return json_error_response(
        status_code=503,
        code="READ_MODEL_CONTRACT_VIOLATION",
        message=str(exc),
        request_id=request_id,
    )


# ============================================================
# Internal token: every request but the health probe
# ============================================================
# core-service trusts the identity headers that the BFF sets (x-identity-id, x-roles): only a caller holding the
# token shared by the services may send them. Registered first, so it runs after the request ID middleware.
_OPEN_PATHS = {"/health"}


@app.middleware("http")
async def internal_token_middleware(request: Request, call_next):
    if request.url.path not in _OPEN_PATHS:
        expected = os.getenv("INTERNAL_TOKEN", "")
        provided = request.headers.get("x-internal-token", "")
        if not expected or not provided or not hmac.compare_digest(provided, expected):
            return json_error_response(
                status_code=401 if not provided else 403,
                request_id=ensure_request_id(request),
                code="INTERNAL_TOKEN_REQUIRED",
                message="This service only answers the other services of BornToShare",
            )
    return await call_next(request)


# ============================================================
# Request ID middleware
# ============================================================

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = ensure_request_id(request)
    # Restore (not clear): orchestration code calls this app's routes in-process within the same request.
    previous_request_id = get_request_id_context()
    set_request_id_context(request_id)
    try:
        response = await call_next(request)
    finally:
        set_request_id_context(previous_request_id)
    response.headers["X-Request-ID"] = request_id
    return response


# ============================================================
# Error handlers (normalized, no leakage)
# ============================================================

register_exception_handlers(app, logger)


# No CORS: browsers never call core-service directly, only the frontend BFF and services do.


# ============================================================
# Health (internal)
# ============================================================

@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",
        "service": settings.SERVICE_NAME,
    }


# ============================================================
# Routers
# ============================================================

# 🔓 Internal auth compatibility surface (auth-service -> core-service direct)
app.include_router(internal_auth_local_router)

# 🌐 API
# - consommée directement par le frontend BFF en mode direct
app.include_router(api_router, prefix=settings.API_PREFIX)

# 🧭 Orchestration (→ Dramatiq jobs for capsule-runner)
app.include_router(governance_router, prefix=settings.API_PREFIX)
