from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, status

from app.core.settings import get_settings
from app.core.internal_auth import build_internal_headers
from app.core.logging import get_logger
from app.schemas.api_envelopes import error_payload

settings = get_settings()
logger = get_logger("governance.dal")


def _retry_delay_seconds(attempt: int) -> float:
    # Small exponential backoff to absorb transient DAL restarts/network flaps.
    base = 0.2
    delay = base * (2 ** max(0, int(attempt) - 1))
    return min(delay, 1.5)


# ============================================================
# Low-level HTTP helper
# ============================================================

async def _request(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 5,
    request_id: Optional[str] = None,
    retries: int = 0,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Any:
    """
    Internal helper to call DAL with internal authentication.
    """
    url = settings.dal_url.rstrip("/") + path
    headers = build_internal_headers()
    headers["X-Service-Name"] = "governance"
    headers["X-Service-Scope"] = "jobs:read,jobs:write,profiles:write,events:write"
    if request_id:
        headers["X-Request-Id"] = request_id
    if extra_headers:
        for key, value in extra_headers.items():
            normalized_key = str(key or "").strip()
            normalized_value = str(value or "").strip()
            if normalized_key and normalized_value:
                headers[normalized_key] = normalized_value

    attempt = 0
    last_exc: Exception | None = None
    max_attempts = max(1, int(retries) + 1)
    while attempt < max_attempts:
        attempt += 1
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.request(method, url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            last_exc = exc
            logger.warning(
                "dal.request.network_error",
                extra={
                    "method": method,
                    "path": path,
                    "timeout": timeout,
                    "attempt": attempt,
                    "request_id": request_id,
                    "error": str(exc)[:500],
                },
            )
            if attempt < max_attempts:
                await asyncio.sleep(_retry_delay_seconds(attempt))
                continue
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=error_payload(
                    code="GOVERNANCE_DAL_FAILURE",
                    message="DAL request failed",
                    request_id=request_id,
                    extra={"attempts": attempt},
                ),
            ) from exc

        if r.status_code >= 400:
            logger.warning(
                "dal.request.http_error",
                extra={
                    "method": method,
                    "path": path,
                    "status": r.status_code,
                    "attempt": attempt,
                    "request_id": request_id,
                },
            )
            if r.status_code in {502, 503, 504} and attempt < max_attempts:
                await asyncio.sleep(_retry_delay_seconds(attempt))
                continue
            detail: Any = "DAL error"
            try:
                detail = r.json()
            except Exception:
                detail = (r.text or "DAL error")[:800]
            raise HTTPException(status_code=r.status_code, detail=detail)

        # Some endpoints may legitimately return no content
        if r.status_code == 204:
            return None

        try:
            return r.json()
        except Exception:
            return {"raw": (r.text or "")[:4000]}


# ============================================================
# Generic DAL helpers
# ============================================================

async def dal_get(
    path: str,
    timeout: int = 5,
    request_id: Optional[str] = None,
    retries: int = 0,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Any:
    return await _request("GET", path, timeout=timeout, request_id=request_id, retries=retries, extra_headers=extra_headers)


async def dal_post(
    path: str,
    payload: Dict[str, Any],
    timeout: int = 5,
    request_id: Optional[str] = None,
    retries: int = 0,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Any:
    return await _request(
        "POST",
        path,
        payload,
        timeout=timeout,
        request_id=request_id,
        retries=retries,
        extra_headers=extra_headers,
    )


async def dal_put(
    path: str,
    payload: Dict[str, Any],
    timeout: int = 5,
    request_id: Optional[str] = None,
    retries: int = 0,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Any:
    return await _request("PUT", path, payload, timeout=timeout, request_id=request_id, retries=retries, extra_headers=extra_headers)


async def dal_patch(
    path: str,
    payload: Dict[str, Any],
    timeout: int = 5,
    request_id: Optional[str] = None,
    retries: int = 0,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Any:
    return await _request("PATCH", path, payload, timeout=timeout, request_id=request_id, retries=retries, extra_headers=extra_headers)


async def dal_delete(
    path: str,
    timeout: int = 5,
    request_id: Optional[str] = None,
    retries: int = 0,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Any:
    return await _request("DELETE", path, timeout=timeout, request_id=request_id, retries=retries, extra_headers=extra_headers)


# Capsules, probes, and advanced settings are not used in V1 governance.
