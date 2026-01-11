from __future__ import annotations

import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger(__name__)

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = rid
        start = time.perf_counter()

        try:
            response: Response = await call_next(request)
        except Exception:
            logger.exception("Unhandled error | rid=%s | %s %s", rid, request.method, request.url.path)
            raise
        finally:
            dur_ms = (time.perf_counter() - start) * 1000.0
            logger.debug("Request done | rid=%s | %s %s | %.1fms", rid, request.method, request.url.path, dur_ms)

        response.headers["x-request-id"] = rid
        return response
