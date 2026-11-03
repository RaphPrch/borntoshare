from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# The server refuses the built-in signing key at startup: the tests start it with their own
os.environ.setdefault("PRINCIPAL_SIGNING_KEY", "tests-principal-signing-key-0123456789abcdef")


@pytest.fixture(autouse=True)
def _no_activity_forwarding(monkeypatch):
    """Audit events go to core-service, which does not run in the tests."""
    from app.api import auth as auth_api

    sent: list[dict] = []

    async def _capture(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(auth_api, "_emit_activity_event", _capture)

    # Startup reads the log level from core-service: not running in the tests
    async def _no_startup_config():
        return None

    monkeypatch.setattr(auth_api, "apply_startup_log_level", _no_startup_config)
    return sent
