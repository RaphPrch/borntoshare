from __future__ import annotations

import pytest

from app.services.providers.base import (
    AuthUnavailable,
    InvalidCredentials,
    ProviderMisconfigured,
    SecretResolutionError,
)
from app.services.providers.ad_ldap import _resolve_bind_password
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


def test_local_provider_401_maps_to_invalid_credentials(monkeypatch):
    import asyncio

    provider = DalLocalProvider()

    import app.services.providers.local_dal as local_module

    monkeypatch.setattr(local_module.httpx, "AsyncClient", lambda **_kwargs: _FakeClient(_FakeResponse(401, {"detail": "invalid"})))

    with pytest.raises(InvalidCredentials):
        asyncio.run(provider.authenticate("u", "p"))


def test_local_provider_503_maps_to_unavailable(monkeypatch):
    import asyncio

    provider = DalLocalProvider()

    import app.services.providers.local_dal as local_module

    monkeypatch.setattr(local_module.httpx, "AsyncClient", lambda **_kwargs: _FakeClient(_FakeResponse(503, {"detail": "down"})))

    with pytest.raises(AuthUnavailable):
        asyncio.run(provider.authenticate("u", "p"))


def test_resolve_bind_password_missing_ref_returns_empty() -> None:
    out = _resolve_bind_password({"bind_password_ref": ""}, target=None)
    assert out == ""


def test_resolve_bind_password_failure_maps_to_secret_resolution(monkeypatch):
    import app.services.providers.ad_ldap as ad_module

    def _fail(*_args, **_kwargs):
        raise RuntimeError("resolver down")

    monkeypatch.setattr(ad_module, "resolve_secret", _fail)
    with pytest.raises(SecretResolutionError):
        _resolve_bind_password({"bind_password_ref": "sm://ad/secret"}, target="corp.local")


def test_local_provider_does_not_map_401_to_provider_misconfigured(monkeypatch):
    import asyncio
    import app.services.providers.local_dal as local_module

    provider = DalLocalProvider()
    monkeypatch.setattr(local_module.httpx, "AsyncClient", lambda **_kwargs: _FakeClient(_FakeResponse(401, {"detail": "invalid"})))

    with pytest.raises(InvalidCredentials):
        asyncio.run(provider.authenticate("u", "p"))

    with pytest.raises(Exception) as exc:
        raise InvalidCredentials("invalid")
    assert not isinstance(exc.value, ProviderMisconfigured)
