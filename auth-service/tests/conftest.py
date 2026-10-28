from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture(autouse=True)
def _no_activity_forwarding(monkeypatch):
    """Audit events go to core-service, which does not run in the tests."""
    from app.api import auth as auth_api

    sent: list[dict] = []

    async def _capture(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(auth_api, "_emit_activity_event", _capture)
    return sent
