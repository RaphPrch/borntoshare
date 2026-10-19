from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services import core_client


def test_headers_require_internal_token(monkeypatch) -> None:
    monkeypatch.delenv("INTERNAL_TOKEN", raising=False)

    with pytest.raises(RuntimeError) as exc:
        core_client._headers()
    assert "INTERNAL_TOKEN" in str(exc.value)


def test_headers_send_internal_token_and_caller_identity(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_TOKEN", "internal-token")

    headers = core_client._headers()

    assert "X-Service-Token" not in headers
    assert headers["X-Internal-Token"] == "internal-token"
    assert headers["X-Service-Name"] == "capsule"
    assert headers["X-Service-Scope"] == "jobs:read,jobs:write,events:write,profiles:write"
