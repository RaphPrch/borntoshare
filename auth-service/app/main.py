from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger
from app.api.auth import router as auth_router
from app.api.health import router as health_router

# -------------------------------------------------
# Init logging
# -------------------------------------------------
setup_logging()
logger = get_logger("auth-service")

settings = get_settings()

app = FastAPI(
    title="BornToShare Auth-Service",
    version=settings.VERSION,
)


# -------------------------------------------------
# Security & error normalization (SecNumCloud L2)
# -------------------------------------------------
import uuid
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex}"

@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    request.state.request_id = _rid(request)
    resp = await call_next(request)
    resp.headers["x-request-id"] = request.state.request_id
    return resp

@app.exception_handler(HTTPException)
async def _http_exc_handler(request: Request, exc: HTTPException):
    code = "HTTP_ERROR"
    if exc.status_code == 401:
        code = "UNAUTHENTICATED"
    elif exc.status_code == 403:
        code = "FORBIDDEN"
    elif exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 409:
        code = "CONFLICT"
    elif exc.status_code == 400:
        code = "BAD_REQUEST"

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": str(exc.detail), "request_id": _rid(request)}},
    )

@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError):
    # Do not leak full details in production modes; keep minimal + request id.
    msg = "Validation failed."
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": msg, "request_id": _rid(request)}},
    )

@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception):
    # Never leak internals to clients
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error.", "request_id": _rid(request)}},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)


# -------------------------------------------------
# Startup: log exposed routes
# -------------------------------------------------
@app.on_event("startup")
async def startup_log_routes() -> None:
    logger.info(
        "Auth-service started | env=%s version=%s",
        settings.APP_ENV,
        settings.VERSION,
    )

    logger.info("Exposed routes:")
    for route in app.routes:
        if isinstance(route, APIRoute):
            methods = ",".join(sorted(route.methods))
            logger.info("  %-6s %s", methods, route.path)
