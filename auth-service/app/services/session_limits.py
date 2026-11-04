"""Session limits (Advanced settings > Sessions) and sign-in limits (Advanced settings > User sessions),
read from core-service and kept one minute."""
from __future__ import annotations

import time

import httpx

from app.core.config import get_settings
from app.core.internal_token import build_internal_headers

DEFAULT_TTL_SECONDS = 8 * 60 * 60
DEFAULT_IDLE_SECONDS = 30 * 60
_CACHE_SECONDS = 60

_limits = (DEFAULT_TTL_SECONDS, DEFAULT_IDLE_SECONDS)
# Failures per account, per address, window in seconds; None until core-service answered (the .env values apply)
_sign_in: tuple[int, int, int] | None = None
_read_at = 0.0


def _refresh() -> None:
    global _limits, _sign_in, _read_at
    _read_at = time.monotonic()
    try:
        url = get_settings().CORE_URL.rstrip("/") + "/api/admin/config/advanced"
        resp = httpx.get(url, headers=build_internal_headers(), timeout=2.0)
        sessions = (resp.json().get("data") or {}).get("sessions") or {}
        if resp.status_code == 200:
            _limits = (int(sessions["ttlSeconds"]), int(sessions["idleSeconds"]))
            sign_in = (resp.json().get("data") or {}).get("signIn") or {}
            if sign_in:
                _sign_in = (int(sign_in["maxFailuresPerAccount"]), int(sign_in["maxFailuresPerAddress"]), int(sign_in["windowMinutes"]) * 60)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        pass  # core-service does not answer: the last known limits stay


def _current() -> tuple[int, int]:
    if not _read_at or time.monotonic() - _read_at > _CACHE_SECONDS:
        _refresh()
    return _limits


def session_ttl_seconds() -> int:
    return _current()[0]


def session_idle_seconds() -> int:
    return _current()[1]


def sign_in_limits(defaults: tuple[int, int, int]) -> tuple[int, int, int]:
    """(failures per account, failures per address, window in seconds)."""
    _current()
    return _sign_in or defaults
