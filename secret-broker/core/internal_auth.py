from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from core.api_envelope import error_payload
from core.settings import settings

def require_internal_token(request: Request) -> None:
    tok = (request.headers.get("X-Internal-Token") or "").strip()
    expected = (settings.internal_token or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_payload(
                code="INTERNAL_ERROR",
                message="Internal token not configured",
                details={},
            ),
        )
    if not hmac.compare_digest(tok, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_payload(
                code="FORBIDDEN",
                message="Forbidden",
                details={},
            ),
        )
