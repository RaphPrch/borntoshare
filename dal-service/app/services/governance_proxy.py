from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException

from app.core.internal_headers import get_internal_headers
from app.core.internal_auth import require_internal_token
from app.core.logging import get_logger, log_event


GOVERNANCE_URL = os.getenv(
    "GOVERNANCE_URL",
    "http://governance-service:8000",
).rstrip("/")
logger = get_logger(__name__)


async def gov_post(
    *,
    request,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
):
    # Enforce internal token (DAL endpoints are internal-only)
    require_internal_token(request)

    headers = {
        **get_internal_headers(request),
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            res = await client.post(
                f"{GOVERNANCE_URL}{path}",
                json=payload,
                params=params,
                headers=headers,
            )
        except httpx.RequestError as exc:
            log_event(
                logger,
                40,
                "DAL_GOVERNANCE_PROXY_FAILED",
                action="governance_post",
                target=path,
                outcome="network_error",
                message=str(exc),
            )
            raise HTTPException(
                status_code=502,
                detail=f"GOVERNANCE connection error: {exc}",
            ) from exc

    if not res.is_success:
        log_event(
            logger,
            40,
            "DAL_GOVERNANCE_PROXY_BAD_RESPONSE",
            action="governance_post",
            target=path,
            outcome="bad_response",
            status_code=res.status_code,
        )
        try:
            detail = res.json()
        except ValueError:
            detail = res.text

        raise HTTPException(
            status_code=res.status_code,
            detail=detail,
        )

    if res.status_code == 204:
        return None

    return res.json()


async def gov_get(
    *,
    request,
    path: str,
    params: Optional[Dict[str, Any]] = None,
):
    require_internal_token(request)

    headers = get_internal_headers(request)

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            res = await client.get(
                f"{GOVERNANCE_URL}{path}",
                params=params,
                headers=headers,
            )
        except httpx.RequestError as exc:
            log_event(
                logger,
                40,
                "DAL_GOVERNANCE_PROXY_FAILED",
                action="governance_get",
                target=path,
                outcome="network_error",
                message=str(exc),
            )
            raise HTTPException(
                status_code=502,
                detail=f"GOVERNANCE connection error: {exc}",
            ) from exc

    if not res.is_success:
        log_event(
            logger,
            40,
            "DAL_GOVERNANCE_PROXY_BAD_RESPONSE",
            action="governance_get",
            target=path,
            outcome="bad_response",
            status_code=res.status_code,
        )
        try:
            detail = res.json()
        except ValueError:
            detail = res.text

        raise HTTPException(
            status_code=res.status_code,
            detail=detail,
        )

    if res.status_code == 204:
        return None

    return res.json()
