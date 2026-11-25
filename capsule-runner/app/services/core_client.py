from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

from app.core import settings


def _headers() -> Dict[str, str]:
    internal_token = (os.getenv("INTERNAL_TOKEN") or "").strip()
    if not internal_token:
        raise RuntimeError("Missing INTERNAL_TOKEN for core-service internal calls")

    headers = {
        "X-Internal-Token": internal_token,
        "X-Service-Name": "capsule",
        "X-Service-Scope": "jobs:read,jobs:write,events:write,profiles:write",
    }
    # Its own token (H4): core-service knows the worker by it and gives it its routes and scopes, whatever it declares
    own = (os.getenv("B2S_SERVICE_TOKEN") or "").strip()
    if own:
        headers["X-Service-Token"] = own
    return headers


def _request(method: str, path: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 10) -> Any:
    url = settings.CORE_URL.rstrip("/") + path
    with httpx.Client(timeout=timeout) as client:
        response = client.request(method, url, json=payload, headers=_headers())
    response.raise_for_status()
    if response.status_code == 204:
        return None
    return response.json() if response.content else None


def core_get(path: str, timeout: int = 10) -> Any:
    return _request("GET", path, timeout=timeout)


def core_post(path: str, payload: Dict[str, Any], timeout: int = 10) -> Any:
    return _request("POST", path, payload=payload, timeout=timeout)
