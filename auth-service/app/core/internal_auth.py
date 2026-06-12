from __future__ import annotations

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


def require_internal_token(x_internal_token: str | None, *, source: str = "internal") -> None:
    expected = (settings.INTERNAL_TOKEN or "").strip()
    provided = (x_internal_token or "").strip()
    if not expected or provided != expected:
        logger.warning(
            "Invalid internal token | source=%s | expected_set=%s got_set=%s",
            source,
            bool(expected),
            bool(provided),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHENTICATED",
                "message": "Invalid internal token",
                "details": {},
            },
        )
