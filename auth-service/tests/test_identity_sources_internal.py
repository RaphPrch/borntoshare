from __future__ import annotations

import asyncio

from fastapi import HTTPException

from app.api import identity_sources as api


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
