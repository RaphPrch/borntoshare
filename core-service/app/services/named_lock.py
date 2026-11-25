"""MariaDB named locks (GET_LOCK) held on their own connection: the work inside commits with its own session, and
the lock is released however the block ends (exception, return)."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import text


class LockBusy(RuntimeError):
    """Another holder kept the lock beyond the wait."""


@contextmanager
def named_lock(name: str, wait_seconds: int):
    from app.core.db import engine

    with engine.connect() as conn:
        if not conn.execute(text("SELECT GET_LOCK(:name, :wait)"), {"name": name, "wait": int(wait_seconds)}).scalar():
            raise LockBusy(name)
        try:
            yield
        finally:
            conn.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})
