"""Failed sign-ins: too many in a row and the next attempts are refused before reaching a directory.

Two counters over a sliding window: one identifier from one address (someone guessing a password),
and one address over every identifier (someone trying a password on many accounts).
Kept in memory: auth-service runs a single process, a restart forgets them.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.config import get_settings

settings = get_settings()


class LoginThrottle:
    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    @staticmethod
    def _keys(username: str, address: str) -> tuple[str, str]:
        return f"user:{str(username or '').strip().lower()}|{address}", f"addr:{address}"

    def _recent(self, key: str, now: float) -> deque[float]:
        attempts = self._failures[key]
        while attempts and attempts[0] <= now - settings.LOGIN_THROTTLE_WINDOW_SECONDS:
            attempts.popleft()
        if not attempts:
            del self._failures[key]
            return deque()
        return attempts

    def retry_after(self, username: str, address: str) -> int:
        """Seconds before the next attempt is allowed; 0 when it is allowed now."""
        now = time.monotonic()
        user_key, address_key = self._keys(username, address)
        wait = 0.0
        for key, limit in (
            (user_key, settings.LOGIN_THROTTLE_MAX_FAILURES),
            (address_key, settings.LOGIN_THROTTLE_MAX_FAILURES_PER_ADDRESS),
        ):
            attempts = self._recent(key, now)
            if len(attempts) >= limit:
                wait = max(wait, attempts[0] + settings.LOGIN_THROTTLE_WINDOW_SECONDS - now)
        return int(wait) + 1 if wait > 0 else 0

    def record_failure(self, username: str, address: str) -> None:
        now = time.monotonic()
        for key in self._keys(username, address):
            self._failures[key].append(now)

    def reset(self, username: str, address: str) -> None:
        """A successful sign-in clears the identifier, not the address (a valid account must not hide guessing)."""
        self._failures.pop(self._keys(username, address)[0], None)


login_throttle = LoginThrottle()
