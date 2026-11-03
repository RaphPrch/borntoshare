from __future__ import annotations

from app.core.config import get_settings
from app.services import login_throttle as module
from app.services.login_throttle import LoginThrottle

settings = get_settings()


def test_blocks_after_the_limit_then_reopens(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    throttle = LoginThrottle()
    for _ in range(settings.LOGIN_THROTTLE_MAX_FAILURES - 1):
        throttle.record_failure("Marc", "10.0.0.1")
    assert throttle.retry_after("marc", "10.0.0.1") == 0

    throttle.record_failure("marc", "10.0.0.1")
    assert throttle.retry_after("MARC ", "10.0.0.1") > 0
    # Someone else, or the same person elsewhere, is not locked out
    assert throttle.retry_after("claire", "10.0.0.1") == 0
    assert throttle.retry_after("marc", "10.0.0.2") == 0

    clock[0] += settings.LOGIN_THROTTLE_WINDOW_SECONDS + 1
    assert throttle.retry_after("marc", "10.0.0.1") == 0


def test_success_clears_the_identifier_but_not_the_address(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_THROTTLE_MAX_FAILURES_PER_ADDRESS", 6)
    throttle = LoginThrottle()
    for _ in range(5):
        throttle.record_failure("marc", "10.0.0.1")
    throttle.reset("marc", "10.0.0.1")
    assert throttle.retry_after("marc", "10.0.0.1") == 0
    throttle.record_failure("other", "10.0.0.1")
    assert throttle.retry_after("anyone", "10.0.0.1") > 0


def test_the_built_in_signing_key_is_refused_at_startup() -> None:
    import pytest

    from app.core.config import DEV_PRINCIPAL_SIGNING_KEY, Settings, require_principal_signing_key

    for key in ("", DEV_PRINCIPAL_SIGNING_KEY):
        with pytest.raises(RuntimeError):
            require_principal_signing_key(Settings(PRINCIPAL_SIGNING_KEY=key))
    require_principal_signing_key(Settings(PRINCIPAL_SIGNING_KEY="a-real-key-0123456789abcdef0123456789"))
