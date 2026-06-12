from __future__ import annotations

import os
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from core.api_envelope import error_payload, ok_data
from routers.secrets import router as secrets_router
from routers.secrets import ensure_boot_checks

APP_NAME = "b2s-secret-broker"

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

def build_app() -> FastAPI:
    ensure_boot_checks()

    app = FastAPI(title=APP_NAME, version="1.0.0")

    @app.get("/health")
    def health():
        return ok_data({"status": "ok", "name": APP_NAME})

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id")
        response = await call_next(request)
        if rid:
            response.headers.setdefault("x-request-id", rid)
        return response

    @app.exception_handler(HTTPException)
    async def normalize_http_exception(_: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and detail.get("ok") is False and isinstance(detail.get("error"), dict):
            return JSONResponse(status_code=exc.status_code, content=detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                code="HTTP_ERROR",
                message=str(detail or "Request failed"),
                details={},
            ),
        )

    app.include_router(secrets_router)
    return app

app = build_app()
