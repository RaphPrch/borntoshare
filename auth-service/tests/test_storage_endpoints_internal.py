from __future__ import annotations

import asyncio

from fastapi import HTTPException

from app.api import storage_endpoints as api


def test_store_storage_endpoint_bind_password_ref_stores_via_backend(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_store_secret(name: str, value: str) -> str:
        calls.append((name, value))
        return "sm://storage-endpoint/smb/fs01/bind-password"

    monkeypatch.setattr(api, "require_internal_token", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api, "store_secret", _fake_store_secret)

    out = asyncio.run(
        api.store_bind_password_ref(
            {
                "name": "FS01",
                "protocol": "smb",
                "host": "fs01.corp.local",
                "bind_dn": "CORP\\svc-files",
                "bind_password": "Secret123!",
            },
            x_internal_token="test-token",
        )
    )

    assert out["bind_password_ref"] == "sm://storage-endpoint/smb/fs01/bind-password"
    assert calls == [("storage-endpoint/smb/fs01/bind-password", "Secret123!")]


def test_store_storage_endpoint_bind_password_ref_reuses_existing_ref(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_store_secret(name: str, value: str) -> str:
        calls.append((name, value))
        return str(name)

    monkeypatch.setattr(api, "require_internal_token", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api, "store_secret", _fake_store_secret)

    out = asyncio.run(
        api.store_bind_password_ref(
            {
                "name": "FS01",
                "protocol": "smb",
                "bind_dn": "CORP\\svc-files",
                "bind_password_ref": "sm://storage-endpoint/smb/fs01/bind-password",
                "bind_password": "NewSecret123!",
            },
            x_internal_token="test-token",
        )
    )

    assert out["bind_password_ref"] == "sm://storage-endpoint/smb/fs01/bind-password"
    assert calls == [("sm://storage-endpoint/smb/fs01/bind-password", "NewSecret123!")]


def test_store_storage_endpoint_bind_password_ref_requires_password(monkeypatch) -> None:
    monkeypatch.setattr(api, "require_internal_token", lambda *_args, **_kwargs: None)

    try:
        asyncio.run(
            api.store_bind_password_ref(
                {
                    "name": "FS01",
                    "protocol": "smb",
                    "bind_dn": "CORP\\svc-files",
                },
                x_internal_token="test-token",
            )
        )
        assert False, "HTTPException expected"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert isinstance(exc.detail, dict)
        assert exc.detail.get("code") == "BAD_REQUEST"
