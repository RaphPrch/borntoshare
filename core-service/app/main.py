from __future__ import annotations


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
    from app.services.modules import warm_fives_installed
    from app.services.otel_export import start_if_enabled

    start_if_enabled()
    # Is the 5S module there? Asked now in a thread: a missing one takes seconds to fail, no request waits for it
    warm_fives_installed()
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
_OPEN_PATHS = {"/health", "/health/live"}


@app.middleware("http")
async def otel_span_middleware(request: Request, call_next):
    """One span per request for OpenTelemetry (Advanced settings › Extensions), when it is enabled."""
    import time as _time

    from app.services.otel_export import record_span

    started = _time.time_ns()
    response = await call_next(request)
    if not request.url.path.startswith("/health"):
        route = getattr(request.scope.get("route"), "path", None) or request.url.path
        record_span(request.method, route, response.status_code, started, _time.time_ns(), request.headers.get("traceparent"))
    return response


@app.middleware("http")
async def internal_token_middleware(request: Request, call_next):
    """The caller is the service whose token is given (app.core.service_identity); a narrow service (worker, 5S
    module) only reaches its own routes."""
    from app.core.service_identity import TOKEN_HEADER, caller_of, path_allowed

    if request.url.path not in _OPEN_PATHS:
        provided = request.headers.get(TOKEN_HEADER) or request.headers.get("x-internal-token")
        caller = caller_of(request.headers.get(TOKEN_HEADER), request.headers.get("x-internal-token"))
        if caller is None:
            return json_error_response(
                status_code=401 if not provided else 403,
                request_id=ensure_request_id(request),
                code="INTERNAL_TOKEN_REQUIRED",
                message="This service only answers the other services of BornToShare",
            )
        if not path_allowed(caller, request.method, request.url.path):
            logger.warning("SERVICE_PATH_FORBIDDEN", extra={"caller": caller, "method": request.method, "path": request.url.path})
            return json_error_response(
                status_code=403,
                request_id=ensure_request_id(request),
                code="SERVICE_PATH_FORBIDDEN",
                message="This service may not call this route",
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
    # Who asks (a person through the BFF): kept with the jobs this request starts
    from app.core.actor_context import reset_actor, set_actor

    actor_token = set_actor(request.headers.get("x-actor-display")) if request.headers.get("x-actor-display") else None
    try:
        response = await call_next(request)
    finally:
        set_request_id_context(previous_request_id)
        if actor_token is not None:
            reset_actor(actor_token)
    response.headers["X-Request-ID"] = request_id
    return response


# ============================================================
# Identity of the person (outermost: registered last)
# ============================================================

_IDENTITY_HEADERS = (b"x-identity-id", b"x-roles", b"x-actor-display")


@app.middleware("http")
async def identity_middleware(request: Request, call_next):
    """With the tokens per service, the person is only the one of a valid signed assertion (X-B2S-Actor): the
    identity headers received are dropped and replaced by its values, before any other code reads them."""
    from app.core.service_identity import ACTOR_HEADER, per_service_mode, verify_actor

    if per_service_mode():
        verified = verify_actor(request.headers.get(ACTOR_HEADER))
        headers = [(k, v) for k, v in request.scope["headers"] if k.lower() not in _IDENTITY_HEADERS]
        if verified is not None:
            if verified.identity_id is not None:
                headers.append((b"x-identity-id", str(verified.identity_id).encode()))
            if verified.roles:
                headers.append((b"x-roles", ",".join(sorted(verified.roles)).encode()))
            if verified.display_name:
                headers.append((b"x-actor-display", verified.display_name.encode("utf-8")))
        request.scope["headers"] = headers
        # Starlette keeps the headers it already read in _headers: read again from the scope
        if hasattr(request, "_headers"):
            del request._headers
    return await call_next(request)


# ============================================================
# Error handlers (normalized, no leakage)
# ============================================================

register_exception_handlers(app, logger)


# No CORS: browsers never call core-service directly, only the frontend BFF and services do.


# ============================================================
# Health (internal)
# ============================================================

@app.get("/health/live", tags=["health"])
def health_live():
    """Liveness: the process answers, whatever its dependencies (a monitor tells « stopped » from « degraded »)."""
    return {"status": "ok", "service": settings.SERVICE_NAME}


@app.get("/health", tags=["health"])
def health():
    """Container healthcheck: answers 503 when the database or the job queue cannot be reached."""
    from fastapi.responses import JSONResponse
    from redis import Redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry
    from sqlalchemy import text

    checks: dict[str, str] = {}
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = str(getattr(exc, "orig", exc))[:200]
    try:
        Redis.from_url(settings.CAPSULE_BROKER_URL, socket_timeout=2, socket_connect_timeout=2, retry=Retry(NoBackoff(), 0)).ping()
        checks["job_queue"] = "ok"
    except Exception as exc:
        checks["job_queue"] = str(exc)[:200]
    healthy = all(value == "ok" for value in checks.values())
    body = {"status": "ok" if healthy else "down", "service": settings.SERVICE_NAME, "checks": checks}
    return body if healthy else JSONResponse(status_code=503, content=body)


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
