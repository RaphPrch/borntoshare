from __future__ import annotations

import asyncio
import importlib
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _new_client(*, raise_server_exceptions: bool = True) -> TestClient:
    app_module = importlib.import_module("app.main")
    return TestClient(app_module.app, raise_server_exceptions=raise_server_exceptions)


def test_login_sets_session_and_principal_cookie_and_no_session_in_body(monkeypatch) -> None:
    from app.api import auth as auth_api
    from app.schemas.auth import UserInfo

    class _Provider:
        name = "local"

        async def authenticate(self, username: str, password: str):
            return UserInfo(
                identity_id="123",
                username=username,
                display_name="User 123",
                email="u123@example.org",
                external_id=None,
                auth_source="local",
                is_admin=True,
                roles=["platform_admin"],
            )

    async def _post_auth(user):
        return user

    async def _attach_roles(user):
        return user

    async def _bind_ad(user):
        return user

    monkeypatch.setattr(auth_api, "choose_provider", lambda _: _Provider())
    monkeypatch.setattr(auth_api, "_post_auth_enrich_user", _post_auth)
    monkeypatch.setattr(auth_api, "_attach_rbac_roles", _attach_roles)
    monkeypatch.setattr(auth_api, "_bind_ad_user_to_local_identity", _bind_ad)
    monkeypatch.setattr(auth_api, "dal_resolve_login_identity", lambda **_kwargs: asyncio.sleep(0, result={"found": False}))

    with _new_client() as client:
        res = client.post(
            "/auth/login",
            json={"username": "user123", "password": "secret", "provider": "local"},
        )

        assert res.status_code == 200
        payload = res.json()
        assert "session" not in payload
        assert "user" in payload

        set_cookie = "; ".join(res.headers.get_list("set-cookie"))
        assert "b2s_session=" in set_cookie
        assert "b2s_principal=" in set_cookie


def test_auth_me_refreshes_principal_cookie(monkeypatch) -> None:
    from app.api import auth as auth_api
    from app.schemas.auth import UserInfo
    from app.services.session_store import SessionRecord
    from datetime import datetime, timezone

    user = UserInfo(
        identity_id="88",
        username="u88",
        display_name="User 88",
        email="u88@example.org",
        external_id=None,
        auth_source="local",
        is_admin=False,
        roles=["user"],
    )

    rec = SessionRecord(
        session_id="sid-88",
        user=user,
        created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(auth_api.store, "get", lambda sid: rec if sid == "sid-88" else None)

    with _new_client() as client:
        client.cookies.set("b2s_session", "sid-88")
        res = client.get("/auth/me")
        assert res.status_code == 200
        set_cookie = "; ".join(res.headers.get_list("set-cookie"))
        assert "b2s_principal=" in set_cookie


def test_logout_clears_both_auth_cookies(monkeypatch) -> None:
    from app.api import auth as auth_api

    deleted: list[str] = []

    def _delete(sid: str) -> None:
        deleted.append(sid)

    monkeypatch.setattr(auth_api.store, "delete", _delete)

    with _new_client() as client:
        client.cookies.set("b2s_session", "sid-x")
        res = client.post("/auth/logout")
        assert res.status_code == 200
        set_cookie = "; ".join(res.headers.get_list("set-cookie"))
        assert "b2s_session=" in set_cookie
        assert "b2s_principal=" in set_cookie
        assert deleted == ["sid-x"]


def test_login_local_invalid_credentials_returns_401(monkeypatch) -> None:
    from app.api import auth as auth_api
    from app.services.providers.base import InvalidCredentials

    class _Provider:
        name = "local"

        async def authenticate(self, username: str, password: str):
            raise InvalidCredentials("Invalid credentials")

    monkeypatch.setattr(auth_api, "choose_provider", lambda _: _Provider())
    monkeypatch.setattr(auth_api, "dal_resolve_login_identity", lambda **_kwargs: asyncio.sleep(0, result={"found": False}))

    with _new_client() as client:
        res = client.post(
            "/auth/login",
            json={"username": "user123", "password": "bad", "provider": "local"},
        )

    assert res.status_code == 401
    payload = res.json()
    assert payload["error"]["code"] == "UNAUTHENTICATED"


def test_login_local_provider_unavailable_returns_503(monkeypatch) -> None:
    from app.api import auth as auth_api
    from app.services.providers.base import AuthUnavailable

    class _Provider:
        name = "local"

        async def authenticate(self, username: str, password: str):
            raise AuthUnavailable("provider down")

    monkeypatch.setattr(auth_api, "choose_provider", lambda _: _Provider())
    monkeypatch.setattr(auth_api, "dal_resolve_login_identity", lambda **_kwargs: asyncio.sleep(0, result={"found": False}))

    with _new_client() as client:
        res = client.post(
            "/auth/login",
            json={"username": "user123", "password": "secret", "provider": "local"},
        )

    assert res.status_code == 503
    payload = res.json()
    assert payload["error"]["code"] == "AUTH_UNAVAILABLE"


def test_me_without_session_returns_401() -> None:
    with _new_client() as client:
        res = client.get("/auth/me")

    assert res.status_code == 401
    payload = res.json()
    assert payload["error"]["code"] == "UNAUTHENTICATED"


def test_internal_introspect_active_and_inactive(monkeypatch) -> None:
    from app.api import auth as auth_api
    from app.schemas.auth import UserInfo
    from app.services.session_store import SessionRecord
    from datetime import datetime, timezone

    user = UserInfo(
        identity_id="88",
        username="u88",
        display_name="User 88",
        email="u88@example.org",
        external_id=None,
        auth_source="local",
        is_admin=False,
        roles=["platform_admin"],
    )
    rec = SessionRecord(
        session_id="sid-88",
        user=user,
        created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(auth_api, "require_internal_token", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth_api.store, "get", lambda sid: rec if sid == "sid-88" else None)

    with _new_client() as client:
        active = client.post("/auth/internal/introspect", json={"session": "sid-88"})
        inactive = client.post("/auth/internal/introspect", json={"session": "missing"})

    assert active.status_code == 200
    assert active.json()["active"] is True
    assert active.json()["authenticated"] is True
    assert active.json()["session_status"] == "active"
    assert active.json()["identity_id"] == "88"
    assert "platform_admin" in active.json()["roles"]
    assert active.json()["auth_source"] == "local"
    assert isinstance(active.json().get("expires_at"), str)
    assert isinstance(active.json().get("user"), dict)

    assert inactive.status_code == 200
    assert inactive.json() == {
        "active": False,
        "authenticated": False,
        "session_status": "inactive",
        "identity_id": None,
        "user": None,
        "auth_source": None,
        "expires_at": None,
        "roles": [],
    }


def test_admin_sessions_contains_masked_session_id(monkeypatch) -> None:
    from app.api import auth as auth_api
    from app.schemas.auth import UserInfo
    from app.services.session_store import SessionRecord
    from datetime import datetime, timezone

    admin = UserInfo(
        identity_id="1",
        username="admin",
        display_name="Admin",
        email="admin@example.org",
        external_id=None,
        auth_source="local",
        is_admin=True,
        roles=["platform_admin"],
    )
    rec = SessionRecord(
        session_id="12345678-1234-1234-1234-123456789abc",
        user=admin,
        created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(auth_api.store, "get", lambda sid: rec if sid == "sid-admin" else None)
    monkeypatch.setattr(auth_api.store, "list", lambda: [rec])

    with _new_client() as client:
        client.cookies.set("b2s_session", "sid-admin")
        res = client.get("/auth/admin/sessions")

    assert res.status_code == 200
    payload = res.json()
    assert payload["sessions"][0]["id"] == "12345678-1234-1234-1234-123456789abc"
    assert payload["sessions"][0]["id_masked"] == "1234...9abc"


def test_admin_logging_contract_reads_and_persists_dal_config(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_TOKEN", "test-token")
    from app.api import auth as auth_api
    from app.schemas.auth import UserInfo
    from app.services.session_store import SessionRecord
    from datetime import datetime, timezone

    admin = UserInfo(
        identity_id="1",
        username="admin",
        display_name="Admin",
        email="admin@example.org",
        external_id=None,
        auth_source="local",
        is_admin=True,
        roles=["platform_admin"],
    )
    rec = SessionRecord(
        session_id="sid-admin",
        user=admin,
        created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(auth_api.store, "get", lambda sid: rec if sid == "sid-admin" else None)
    captured: dict[str, dict] = {}

    async def _fake_dal_get(_path: str):
        return {
            "data": {
                "logging": {
                    "level": "INFO",
                    "retentionEnabled": True,
                    "retentionDays": 180,
                }
            }
        }

    async def _fake_dal_post(_path: str, payload: dict):
        captured["payload"] = dict(payload or {})
        return {"data": {"ok": True}}

    monkeypatch.setattr(auth_api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(auth_api, "dal_post", _fake_dal_post)

    with _new_client() as client:
        client.cookies.set("b2s_session", "sid-admin")
        get_res = client.get("/auth/admin/logging")
        put_res = client.put("/auth/admin/logging", json={"level": "WARN", "retentionDays": 30})

    assert get_res.status_code == 200
    assert get_res.json()["level"] == "INFO"
    assert get_res.json()["retentionEnabled"] is True
    assert get_res.json()["retentionDays"] == 180
    assert put_res.status_code == 200
    assert put_res.json()["ok"] is True
    assert put_res.json()["level"] == "WARN"
    assert put_res.json()["retentionDays"] == 30
    assert captured["payload"]["logging"]["level"] == "WARN"


def test_login_ad_success(monkeypatch) -> None:
    from app.api import auth as auth_api
    from app.schemas.auth import UserInfo

    class _Provider:
        name = "ad"

        async def authenticate_for_source(self, *, source_id: int, username: str, password: str):
            assert source_id == 2
            return UserInfo(
                identity_id=None,
                username=username,
                display_name="AD User",
                email="ad.user@example.org",
                external_id="guid-1",
                auth_source="ad",
                is_admin=False,
                roles=[],
            )

    async def _bind_ad(user):
        user.identity_id = "1001"
        return user

    async def _post_auth(user):
        return user

    async def _attach_roles(user):
        user.roles = ["user"]
        return user

    async def _resolve_login_identity(**_kwargs):
        return {
            "found": True,
            "identity_id": "1001",
            "username": "b2s",
            "display_name": "b2s",
            "email": None,
            "auth_source": "ad",
            "source_id": 2,
            "external_id": "guid-1",
            "is_active": True,
            "status": "active",
            "type": "user",
            "provisioning_source": "explicit",
        }

    monkeypatch.setattr(auth_api, "choose_provider", lambda _: _Provider())
    monkeypatch.setattr(auth_api, "_bind_ad_user_to_local_identity", _bind_ad)
    monkeypatch.setattr(auth_api, "_post_auth_enrich_user", _post_auth)
    monkeypatch.setattr(auth_api, "_attach_rbac_roles", _attach_roles)
    monkeypatch.setattr(auth_api, "dal_resolve_login_identity", _resolve_login_identity)

    with _new_client() as client:
        res = client.post(
            "/auth/login",
            json={"username": "b2s", "password": "secret"},
        )

    assert res.status_code == 200
    payload = res.json()
    assert payload["user"]["auth_source"] == "ad"
    assert payload["user"]["identity_id"] == "1001"


def test_login_ad_bind_failure_returns_401(monkeypatch) -> None:
    from app.api import auth as auth_api
    from app.services.providers.base import InvalidCredentials

    class _Provider:
        name = "ad"

        async def authenticate_for_source(self, *, source_id: int, username: str, password: str):
            raise InvalidCredentials("Invalid credentials")

    monkeypatch.setattr(auth_api, "choose_provider", lambda _: _Provider())
    monkeypatch.setattr(
        auth_api,
        "dal_resolve_login_identity",
        lambda **_kwargs: asyncio.sleep(
            0,
            result={
                "found": True,
                "identity_id": "1001",
                "username": "b2s",
                "auth_source": "ad",
                "source_id": 2,
                "is_active": True,
                "status": "active",
                "type": "user",
                "provisioning_source": "explicit",
            },
        ),
    )

    with _new_client() as client:
        res = client.post(
            "/auth/login",
            json={"username": "b2s", "password": "bad"},
        )

    assert res.status_code == 401
    payload = res.json()
    assert payload["error"]["code"] == "UNAUTHENTICATED"


def test_login_ad_identity_inactive_returns_403(monkeypatch) -> None:
    from app.api import auth as auth_api

    monkeypatch.setattr(
        auth_api,
        "dal_resolve_login_identity",
        lambda **_kwargs: asyncio.sleep(
            0,
            result={
                "found": True,
                "identity_id": "1001",
                "username": "b2s",
                "auth_source": "ad",
                "source_id": 2,
                "is_active": False,
                "status": "inactive",
                "type": "user",
                "provisioning_source": "explicit",
            },
        ),
    )

    with _new_client() as client:
        res = client.post(
            "/auth/login",
            json={"username": "b2s", "password": "secret"},
        )

    assert res.status_code == 403
    payload = res.json()
    assert payload["error"]["code"] == "FORBIDDEN"


def test_validation_error_has_normalized_contract() -> None:
    with _new_client() as client:
        res = client.post(
            "/auth/login",
            json={"username": "user-only"},
        )

    assert res.status_code == 422
    payload = res.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(payload["error"]["details"], dict)
    assert isinstance(payload["error"]["request_id"], str)
    assert payload["error"]["request_id"]


def test_request_id_generated_when_absent() -> None:
    with _new_client() as client:
        res = client.get("/health")

    assert res.status_code == 200
    rid = res.headers.get("X-Request-ID")
    assert isinstance(rid, str)
    assert rid
    uuid.UUID(rid)


def test_request_id_propagated_when_present() -> None:
    request_id = "test-request-id-123"
    with _new_client() as client:
        res = client.get("/health", headers={"X-Request-ID": request_id})

    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == request_id


def test_http_exception_has_standard_error_contract_and_request_id() -> None:
    request_id = "rid-http-401"
    with _new_client() as client:
        res = client.get("/auth/me", headers={"X-Request-ID": request_id})

    assert res.status_code == 401
    payload = res.json()
    assert set(payload.keys()) == {"error"}
    assert payload["error"]["code"] == "UNAUTHENTICATED"
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["request_id"] == request_id
    assert isinstance(payload["error"]["details"], dict)


def test_unhandled_exception_maps_to_internal_error_contract(monkeypatch) -> None:
    from datetime import datetime, timezone

    from app.api import auth as auth_api
    from app.schemas.auth import UserInfo
    from app.services.session_store import SessionRecord

    user = UserInfo(
        identity_id="42",
        username="u42",
        display_name="User 42",
        email="u42@example.org",
        external_id=None,
        auth_source="local",
        roles=["user"],
    )
    rec = SessionRecord(
        session_id="sid-42",
        user=user,
        created_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(auth_api.store, "get", lambda sid: rec if sid == "sid-42" else None)
    monkeypatch.setattr(auth_api, "_set_principal_cookie", _boom)

    with _new_client(raise_server_exceptions=False) as client:
        client.cookies.set("b2s_session", "sid-42")
        res = client.get("/auth/me")

    assert res.status_code == 500
    payload = res.json()
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert payload["error"]["message"] == "Internal server error."
    assert isinstance(payload["error"]["details"], dict)
    assert isinstance(payload["error"]["request_id"], str)
    assert payload["error"]["request_id"]


def test_login_provider_misconfigured_maps_to_500(monkeypatch) -> None:
    from app.api import auth as auth_api
    from app.services.providers.base import ProviderMisconfigured

    class _Provider:
        name = "ad"

        async def authenticate_for_source(self, *, source_id: int, username: str, password: str):
            raise ProviderMisconfigured("bad config")

    monkeypatch.setattr(auth_api, "choose_provider", lambda _: _Provider())
    monkeypatch.setattr(
        auth_api,
        "dal_resolve_login_identity",
        lambda **_kwargs: asyncio.sleep(
            0,
            result={
                "found": True,
                "identity_id": "1001",
                "username": "b2s",
                "auth_source": "ad",
                "source_id": 2,
                "is_active": True,
                "status": "active",
                "type": "user",
                "provisioning_source": "explicit",
            },
        ),
    )

    with _new_client() as client:
        res = client.post(
            "/auth/login",
            json={"username": "b2s", "password": "secret"},
        )

    assert res.status_code == 500
    payload = res.json()
    assert payload["error"]["code"] == "PROVIDER_MISCONFIGURED"
    assert isinstance(payload["error"]["details"], dict)


def test_login_secret_resolution_error_maps_to_503(monkeypatch) -> None:
    from app.api import auth as auth_api
    from app.services.providers.base import SecretResolutionError

    class _Provider:
        name = "ad"

        async def authenticate_for_source(self, *, source_id: int, username: str, password: str):
            raise SecretResolutionError("secret fail")

    monkeypatch.setattr(auth_api, "choose_provider", lambda _: _Provider())
    monkeypatch.setattr(
        auth_api,
        "dal_resolve_login_identity",
        lambda **_kwargs: asyncio.sleep(
            0,
            result={
                "found": True,
                "identity_id": "1001",
                "username": "b2s",
                "auth_source": "ad",
                "source_id": 2,
                "is_active": True,
                "status": "active",
                "type": "user",
                "provisioning_source": "explicit",
            },
        ),
    )

    with _new_client() as client:
        res = client.post(
            "/auth/login",
            json={"username": "b2s", "password": "secret"},
        )

    assert res.status_code == 503
    payload = res.json()
    assert payload["error"]["code"] == "AUTH_UNAVAILABLE"
    assert isinstance(payload["error"]["details"], dict)


def test_bind_ad_user_to_local_identity_passes_identity_source_id(monkeypatch) -> None:
    from app.api import auth as auth_api
    from app.schemas.auth import UserInfo

    captured: dict[str, object] = {}

    async def _fake_resolve_ad_identity(**kwargs):
        captured.update(kwargs)
        return {
            "found": True,
            "identity_id": "321",
            "is_active": True,
            "display_name": "Alice",
            "email": "alice@corp.local",
        }

    monkeypatch.setattr(auth_api, "dal_resolve_ad_identity", _fake_resolve_ad_identity)

    user = UserInfo(
        identity_id=None,
        identity_source_id=9,
        username="alice",
        display_name=None,
        email=None,
        external_id="guid-1",
        auth_source="ad",
        roles=[],
    )

    out = asyncio.run(auth_api._bind_ad_user_to_local_identity(user))

    assert out.identity_id == "321"
    assert captured["identity_source_id"] == 9
    assert captured["external_id"] == "guid-1"


def test_internal_token_error_contract_is_normalized() -> None:
    with _new_client() as client:
        res = client.post(
            "/auth/internal/introspect",
            json={"session": "sid-any"},
            headers={"X-Internal-Token": "wrong"},
        )

    assert res.status_code == 401
    payload = res.json()
    assert payload["error"]["code"] == "UNAUTHENTICATED"
    assert payload["error"]["message"] == "Invalid internal token"
    assert isinstance(payload["error"]["details"], dict)
