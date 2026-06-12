from __future__ import annotations

import asyncio

from fastapi import HTTPException

from app.api import identity_sources as api


def test_internal_test_identity_source_delegates_to_dal(monkeypatch) -> None:
    calls: list[tuple[str, str, dict]] = []

    async def _fake_dal_request(method: str, path: str, payload=None):
        calls.append((method, path, dict(payload or {})))
        return {
            "ok": True,
            "checks": [
                {"key": "tcp_connect", "ok": True, "message": "ok"},
            ],
        }

    monkeypatch.setattr(api, "require_internal_token", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api, "_dal_request", _fake_dal_request)

    out = asyncio.run(
        api.test_identity_source_internal(
            {
                "type": "ad",
                "host": "dc01.corp.local",
                "base_dn": "DC=corp,DC=local",
                "bind_dn": "CN=svc,OU=Users,DC=corp,DC=local",
                "bind_password_ref": "sm://ad/svc",
            },
            x_internal_token="test-token",
        )
    )

    assert out["ok"] is True
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/api/identity-sources/test"
    assert calls[0][2]["host"] == "dc01.corp.local"
    assert "bind_password" not in calls[0][2]


def test_internal_test_identity_source_never_stores_secret(monkeypatch) -> None:
    secret_store_calls: list[tuple[str, str]] = []

    async def _fake_dal_request(method: str, path: str, payload=None):
        return {"ok": True}

    def _fake_store_secret(name: str, value: str) -> str:
        secret_store_calls.append((name, value))
        return "sm://never/used"

    monkeypatch.setattr(api, "require_internal_token", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api, "_dal_request", _fake_dal_request)
    monkeypatch.setattr(api, "store_secret", _fake_store_secret)

    out = asyncio.run(
        api.test_identity_source_internal(
            {
                "type": "ad",
                "host": "dc01.corp.local",
                "base_dn": "DC=corp,DC=local",
                "bind_dn": "CN=svc,OU=Users,DC=corp,DC=local",
                "bind_password": "Secret123!",
            },
            x_internal_token="test-token",
        )
    )

    assert out["ok"] is True
    assert secret_store_calls == []


def test_store_bind_password_ref_requires_bind_password(monkeypatch) -> None:
    monkeypatch.setattr(api, "require_internal_token", lambda *_args, **_kwargs: None)

    try:
        asyncio.run(
            api.store_bind_password_ref(
                {
                    "type": "ad",
                    "host": "dc01.corp.local",
                    "base_dn": "DC=corp,DC=local",
                    "bind_dn": "CN=svc,OU=Users,DC=corp,DC=local",
                },
                x_internal_token="test-token",
            )
        )
        assert False, "HTTPException expected"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert isinstance(exc.detail, dict)
        assert exc.detail.get("code") == "BAD_REQUEST"
