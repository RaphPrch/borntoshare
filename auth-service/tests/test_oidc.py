from __future__ import annotations

import asyncio
import base64
import json
import time

import pytest

from app.api import sso as sso_api
from app.services import oidc

PROVIDER = {"id": 7, "base_url": "https://sso.example.com", "realm": "example", "client_id": "borntoshare", "verify_tls": True}
CONFIG = {
    "issuer": "https://sso.example.com/realms/example",
    "authorization_endpoint": "https://sso.example.com/auth",
    "token_endpoint": "https://sso.example.com/token",
    "userinfo_endpoint": "https://sso.example.com/userinfo",
}


def _jwt(claims: dict) -> str:
    def enc(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'RS256'})}.{enc(claims)}.sig"


class _Resp:
    def __init__(self, status: int, body: dict) -> None:
        self.status_code = status
        self._body = body
        self.content = json.dumps(body).encode()

    def json(self) -> dict:
        return self._body


def _fake_client(token_resp: _Resp, userinfo: dict | None = None):
    class _Client:
        def __init__(self, *a, **kw) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, data=None):
            _Client.posted = data
            return token_resp

        async def get(self, url, headers=None):
            return _Resp(200, userinfo or {})

    return _Client


def _pending(nonce: str = "n-1") -> oidc.PendingLogin:
    return oidc.PendingLogin(provider_id=7, nonce=nonce, code_verifier="v" * 64, redirect_uri="https://b2s.example.com/sso/callback", return_to="/dashboard", created_at=time.time())


def _id_token(**overrides) -> str:
    claims = {"iss": CONFIG["issuer"], "aud": "borntoshare", "exp": time.time() + 300, "nonce": "n-1", "sub": "u-1", "preferred_username": "alice"}
    claims.update(overrides)
    return _jwt(claims)


@pytest.fixture(autouse=True)
def _discovery(monkeypatch):
    async def _config(provider, fresh=False):
        return CONFIG

    monkeypatch.setattr(oidc, "discovery", _config)


def _exchange(monkeypatch, id_token: str, access_claims: dict | None = None, userinfo: dict | None = None):
    tokens = {"id_token": id_token, "access_token": _jwt(access_claims or {"realm_access": {"roles": ["b2s-admins"]}})}
    monkeypatch.setattr(oidc.httpx, "AsyncClient", _fake_client(_Resp(200, tokens), userinfo))
    return asyncio.run(oidc.exchange_code(PROVIDER, "secret", _pending(), code="c-1"))


def test_a_valid_sign_in_merges_the_token_claims(monkeypatch) -> None:
    claims = _exchange(monkeypatch, _id_token(), userinfo={"sub": "u-1", "email": "alice@example.com"})

    assert claims["preferred_username"] == "alice"
    assert claims["email"] == "alice@example.com"
    assert oidc.claim_values(claims, "realm_access.roles") == ["b2s-admins"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://evil.example.com/realms/example"},
        {"aud": "other-client"},
        {"exp": time.time() - 3600},
        {"nonce": "replayed"},
    ],
)
def test_id_tokens_from_elsewhere_or_replayed_are_refused(monkeypatch, overrides) -> None:
    with pytest.raises(oidc.OidcError) as exc:
        _exchange(monkeypatch, _id_token(**overrides))
    assert exc.value.code == "SSO_TOKEN_INVALID"


def test_userinfo_of_another_user_is_refused(monkeypatch) -> None:
    with pytest.raises(oidc.OidcError):
        _exchange(monkeypatch, _id_token(), userinfo={"sub": "someone-else"})


def test_the_code_exchange_sends_the_pkce_verifier(monkeypatch) -> None:
    _exchange(monkeypatch, _id_token())
    posted = oidc.httpx.AsyncClient.posted
    assert posted["code_verifier"] == "v" * 64
    assert posted["client_secret"] == "secret"


def test_a_rejected_client_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(oidc.httpx, "AsyncClient", _fake_client(_Resp(401, {"error": "invalid_client"})))
    with pytest.raises(oidc.OidcError) as exc:
        asyncio.run(oidc.exchange_code(PROVIDER, "wrong", _pending(), code="c-1"))
    assert exc.value.code == "SSO_CLIENT_REJECTED"


def test_the_authorization_url_carries_state_nonce_and_pkce() -> None:
    url = asyncio.run(oidc.authorization_url(PROVIDER, redirect_uri="https://b2s.example.com/sso/callback", return_to="/storage-roots"))
    from urllib.parse import parse_qs, urlsplit

    params = parse_qs(urlsplit(url).query)
    assert params["code_challenge_method"] == ["S256"]
    pending = oidc.state_store.pop(params["state"][0])
    assert pending is not None and pending.nonce == params["nonce"][0]
    assert pending.return_to == "/storage-roots"
    # A state is used once
    assert oidc.state_store.pop(params["state"][0]) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [("/storage-roots", "/storage-roots"), ("https://evil.example.com", "/dashboard"), ("//evil.example.com", "/dashboard"), (None, "/dashboard")],
)
def test_return_to_stays_on_this_site(value, expected) -> None:
    assert sso_api._safe_return_to(value) == expected


def test_claim_values_reads_client_roles_and_groups() -> None:
    claims = {"resource_access": {"borntoshare": {"roles": ["admin"]}}, "groups": ["/b2s-admins"]}
    assert oidc.claim_values(claims, "resource_access.borntoshare.roles") == ["admin"]
    assert oidc.claim_values(claims, "groups") == ["/b2s-admins"]
    assert oidc.claim_values(claims, "missing.path") == []
