from __future__ import annotations

from dramatiq.middleware import CurrentMessage

from app.jobs.broker import broker


def test_current_message_middleware_is_registered() -> None:
    middlewares = list(getattr(broker, "middleware", []) or [])
    assert any(isinstance(mw, CurrentMessage) for mw in middlewares)

