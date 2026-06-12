from __future__ import annotations

import asyncio

import pytest

from app.core.principal_snapshot import principal_payload_from_user
from app.schemas.auth import UserInfo
from app.services.providers.base import AuthUnavailable
from app.services.providers.local_dal import DalLocalProvider


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}"
        self.text = ""

    def json(self):
        return self._payload or {}


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *_args, **_kwargs):
        return self._response


def test_principal_snapshot_requires_identity_id() -> None:
    user = UserInfo(
        identity_id=None,
        username="alice",
        display_name="Alice",
        email="alice@example.org",
        external_id="ext-1",
        auth_source="ad",
        roles=["user"],
    )

    with pytest.raises(ValueError):
        principal_payload_from_user(user)


def test_local_provider_rejects_contract_without_identity_id(monkeypatch) -> None:
    import app.services.providers.local_dal as local_module

    provider = DalLocalProvider()
    monkeypatch.setattr(
        local_module.httpx,
        "AsyncClient",
        lambda **_kwargs: _FakeClient(_FakeResponse(200, {"id": "77", "username": "u"})),
    )

    with pytest.raises(AuthUnavailable):
        asyncio.run(provider.authenticate("u", "p"))
