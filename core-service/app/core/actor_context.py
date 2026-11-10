"""Who made the current request (the name the BFF sends), for what is recorded along the way: the jobs it starts."""
from __future__ import annotations

from contextvars import ContextVar

_actor: ContextVar[str | None] = ContextVar("b2s_actor_display", default=None)


def set_actor(value: str | None):
    return _actor.set((value or "").strip()[:128] or None)


def reset_actor(token) -> None:
    _actor.reset(token)


def current_actor() -> str | None:
    return _actor.get()
