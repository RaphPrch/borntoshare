from __future__ import annotations

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

app = FastAPI(**settings.fastapi_kwargs())


@app.exception_handler(AccessRequestsReadModelContractError)
async def _access_requests_read_model_contract_handler(request: Request, exc: AccessRequestsReadModelContractError):
    request_id = ensure_request_id(request)
    return json_error_response(
        status_code=503,
        code="READ_MODEL_CONTRACT_VIOLATION",
        message=str(exc),
        request_id=request_id,
    )


@app.on_event("startup")
def _startup_schema_contract_guard() -> None:
    db = SessionLocal()
    try:
        ensure_schema_contract_checked(bind=db.get_bind())
    finally:
        db.close()


@app.on_event("startup")
async def _startup_jobs_watchdog() -> None:
    start_jobs_watchdog()


@app.on_event("startup")
async def _startup_infra_scheduler() -> None:
    start_infra_scheduler()


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
        "env": settings.APP_ENV,
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
