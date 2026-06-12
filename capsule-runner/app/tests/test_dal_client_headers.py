from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services import dal_client


def test_headers_require_service_and_internal_tokens(monkeypatch) -> None:
    monkeypatch.delenv("SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("INTERNAL_TOKEN", raising=False)

    with pytest.raises(RuntimeError) as exc:
        dal_client._headers()
    assert "SERVICE_TOKEN" in str(exc.value)


def test_headers_use_strict_token_sources(monkeypatch) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", "svc-token")
    monkeypatch.setenv("INTERNAL_TOKEN", "internal-token")

    headers = dal_client._headers()

    assert headers["X-Service-Token"] == "svc-token"
    assert headers["X-Internal-Token"] == "internal-token"
    assert headers["X-Service-Name"] == "capsule"
    assert headers["X-Service-Scope"] == "jobs:read,jobs:write,events:write,profiles:write"
