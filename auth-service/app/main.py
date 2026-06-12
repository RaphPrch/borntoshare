from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.core.config import get_settings
from app.core.errors import ensure_request_id, register_exception_handlers
from app.core.logging import (
    clear_request_id_context,
    get_logger,
    log_event,
    set_request_id_context,
    setup_logging,
)
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.identity_sources import router as identity_sources_router
from app.api.storage_endpoints import router as storage_endpoints_router

# -------------------------------------------------
# Init logging
# -------------------------------------------------
setup_logging()
logger = get_logger("auth-service")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event(
        logger,
        logging.INFO,
        "AUTH_SERVICE_STARTUP",
        env=settings.APP_ENV,
        version=settings.VERSION,
    )
    for route in app.routes:
        if isinstance(route, APIRoute):
            methods = ",".join(sorted(route.methods))
            log_event(
                logger,
                logging.INFO,
                "AUTH_ROUTE_EXPOSED",
                methods=methods,
                path=route.path,
            )
    yield
    log_event(
        logger,
        logging.INFO,
        "AUTH_SERVICE_SHUTDOWN",
    )


app = FastAPI(
    title="BornToShare Auth-Service",
    version=settings.VERSION,
    lifespan=lifespan,
)


@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    request_id = ensure_request_id(request)
    set_request_id_context(request_id)
    try:
        resp = await call_next(request)
    finally:
        clear_request_id_context()
    resp.headers["X-Request-ID"] = request_id
    return resp


register_exception_handlers(app, logger)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(identity_sources_router)
app.include_router(storage_endpoints_router)
