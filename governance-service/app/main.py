from __future__ import annotations

import asyncio
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.errors import ensure_request_id, register_exception_handlers
from app.core.settings import get_settings
from app.core.logging import configure_logging
from app.core.internal_guard import InternalGuardMiddleware
from app.schemas.api_envelopes import ok_data
from app.routes.health import router as health_router
from app.api.probes import router as probes_router
from app.api.provisioning import router as provisioning_router
from app.api.provisioning import run_queued_jobs_watchdog_once
from app.api.identity_orchestration import router as identity_orchestration_router
from app.api.audit import router as audit_router
from app.api.access_requests import router as access_requests_router

# ======================================================
# Bootstrap
# ======================================================

settings = get_settings()
configure_logging()

app = FastAPI(
    title="BornToShare Governance Service",
    version="0.1.0",
)

# ======================================================
# Request ID (trace / correlation)
# ======================================================

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = ensure_request_id(request)
    request.state.request_id = rid

    response = await call_next(request)
    response.headers.setdefault("x-request-id", rid)
    return response


# ======================================================
# Security
# ======================================================

# 🔐 Global internal guard (deny-by-default)
# - Direct mode can expose public governance routes through frontend-service
# - Internal routes stay protected by the internal token guard
app.add_middleware(InternalGuardMiddleware)

# ======================================================
# CORS (disabled by default)
# ======================================================

if settings.cors_allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=[
            "Content-Type",
            "X-Internal-Token",
            "X-Request-Id",
        ],
    )

register_exception_handlers(app, logging.getLogger("governance.main"))

# ======================================================
# Routers
# ======================================================

# Public / infra
app.include_router(health_router, tags=["health"])

# Core APIs
app.include_router(probes_router)
app.include_router(provisioning_router)
app.include_router(identity_orchestration_router)
app.include_router(audit_router)
app.include_router(access_requests_router)


async def _jobs_watchdog_loop() -> None:
    while True:
        await asyncio.sleep(max(5, int(settings.job_watchdog_interval_seconds)))
        if not bool(settings.job_watchdog_enabled):
            continue
        correlation_id = f"jobwatchdog_{uuid.uuid4().hex}"
        try:
            await run_queued_jobs_watchdog_once(
                queued_timeout_seconds=int(settings.job_watchdog_queued_timeout_seconds),
                max_republish_count=int(settings.job_watchdog_max_republish),
                limit=int(settings.job_watchdog_limit),
                correlation_id=correlation_id,
            )
        except Exception:
            # Watchdog must never crash the service loop.
            continue


@app.on_event("startup")
async def _jobs_watchdog_startup() -> None:
    if bool(settings.job_watchdog_enabled):
        asyncio.create_task(_jobs_watchdog_loop())

# ======================================================
# Liveness (k8s / podman / docker)
# ======================================================

@app.get("/healthz")
def healthz():
    return ok_data({
        "ok": True,
        "service": "governance-service",
        "ts": int(time.time()),
    })
