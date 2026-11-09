"""What the module asks the core (internal API, shared token): the license, and the folders the person may see.
The module never reads the database of the core."""
from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.auth import Actor
from app.config import settings

_license: dict[str, Any] = {"at": 0.0, "value": None}


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    return {"x-internal-token": settings.INTERNAL_TOKEN, **(extra or {})}


def _get(path: str, *, params: dict | None = None, headers: dict[str, str] | None = None, timeout: float = 20) -> Any:
    try:
        response = httpx.get(f"{settings.B2S_CORE_URL.rstrip('/')}{path}", params=params, headers=_headers(headers), timeout=timeout)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"error_code": "CORE_UNREACHABLE", "message": "BornToShare core is unreachable"}) from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.json().get("detail") if response.headers.get("content-type", "").startswith("application/json") else response.text)
    body = response.json()
    return body.get("data", body) if isinstance(body, dict) else body


def license_state() -> dict[str, Any]:
    """Is the module licensed and switched on (kept LICENSE_CACHE_SECONDS)."""
    now = time.monotonic()
    if _license["value"] is None or now - _license["at"] > settings.LICENSE_CACHE_SECONDS:
        _license["value"] = _get("/api/internal/modules/fives/license", timeout=5)
        _license["at"] = now
    return _license["value"]


def require_license() -> dict[str, Any]:
    state = license_state()
    if not state.get("enabled"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "error_code": "FEATURE_DISABLED", "message": "This feature is not active: an administrator turns it on in Advanced settings › Features",
            "feature": "fives"})
    return state


def folders(actor: Actor, *, zone_id: int | None = None, root_id: int | None = None) -> list[dict[str, Any]]:
    """The governed folders the person may see, with what the core knows of them (content, guardians, tags…)."""
    params = {key: value for key, value in (("zone_id", zone_id), ("root_id", root_id)) if value}
    return list(_get("/api/internal/modules/fives/folders", params=params, headers=actor.headers()) or [])
