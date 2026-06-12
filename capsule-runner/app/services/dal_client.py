from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

from app.core import settings


def _headers() -> Dict[str, str]:
    service_token = (
        os.getenv("SERVICE_TOKEN")
        or ""
    ).strip()

    # Security hardening:
    # - X-Service-Token is only sourced from SERVICE_TOKEN (strict separation)
    # - X-Internal-Token is only sourced from INTERNAL_TOKEN
    internal_token = (os.getenv("INTERNAL_TOKEN") or "").strip()

    if not service_token:
        raise RuntimeError("Missing SERVICE_TOKEN for DAL internal calls")
    if not internal_token:
        raise RuntimeError("Missing INTERNAL_TOKEN for DAL internal calls")

    return {
        "X-Service-Token": service_token,
        "X-Internal-Token": internal_token,
        "X-Service-Name": "capsule",
        "X-Service-Scope": "jobs:read,jobs:write,events:write,profiles:write",
    }


def _request(method: str, path: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 10) -> Any:
    url = settings.DAL_URL.rstrip("/") + path
    with httpx.Client(timeout=timeout) as client:
        response = client.request(method, url, json=payload, headers=_headers())
    response.raise_for_status()
    if response.status_code == 204:
        return None
    return response.json() if response.content else None


def dal_get(path: str, timeout: int = 10) -> Any:
    return _request("GET", path, timeout=timeout)


def dal_post(path: str, payload: Dict[str, Any], timeout: int = 10) -> Any:
    return _request("POST", path, payload=payload, timeout=timeout)


def dal_patch(path: str, payload: Dict[str, Any], timeout: int = 10) -> Any:
    return _request("PATCH", path, payload=payload, timeout=timeout)
