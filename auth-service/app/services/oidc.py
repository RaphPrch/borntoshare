"""OpenID Connect sign-in with Keycloak (authorization code + PKCE).

The tokens are received directly from the token endpoint, over TLS, with client authentication: per
OpenID Connect Core 3.1.3.7, the TLS validation of the issuer then stands in for the signature check.
The issuer, audience, expiry and nonce of the ID token are always checked.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import ssl
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings

settings = get_settings()

STATE_TTL_SECONDS = 600
DISCOVERY_TTL_SECONDS = 600


class OidcError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _verify(provider: dict[str, Any]) -> Any:
    if not provider.get("verify_tls", True):
        return False
    ca_file = (os.getenv("B2S_OIDC_CA_FILE") or "").strip()
    if ca_file and os.path.isfile(ca_file):
        return ssl.create_default_context(cafile=ca_file)
    return True


def issuer_url(provider: dict[str, Any]) -> str:
    return f"{str(provider['base_url']).rstrip('/')}/realms/{provider['realm']}"


# ---------------------------------------------------------------- discovery

_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}


async def discovery(provider: dict[str, Any], *, fresh: bool = False) -> dict[str, Any]:
    url = f"{issuer_url(provider)}/.well-known/openid-configuration"
    cached = _discovery_cache.get(url)
    if cached and not fresh and cached[0] > time.time():
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=8.0, verify=_verify(provider)) as client:
            resp = await client.get(url)
    except httpx.ConnectError as exc:
        if "certificate" in str(exc).lower():
            raise OidcError("SSO_TLS_FAILED", "Certificate of the Keycloak server refused (B2S_OIDC_CA_FILE, or uncheck “Verify certificate”)") from exc
        raise OidcError("SSO_UNREACHABLE", f"Keycloak unreachable at {url}") from exc
    except httpx.HTTPError as exc:
        raise OidcError("SSO_UNREACHABLE", f"Keycloak unreachable at {url}: {exc}") from exc
    if resp.status_code == 404:
        raise OidcError("SSO_REALM_NOT_FOUND", f"Realm “{provider['realm']}” not found on {provider['base_url']}")
    if resp.status_code != 200:
        raise OidcError("SSO_UNREACHABLE", f"Keycloak answered HTTP {resp.status_code} on {url}")
    data = resp.json()
    for key in ("issuer", "authorization_endpoint", "token_endpoint"):
        if not data.get(key):
            raise OidcError("SSO_DISCOVERY_INVALID", f"OpenID configuration without {key}")
    _discovery_cache[url] = (time.time() + DISCOVERY_TTL_SECONDS, data)
    return data


# ---------------------------------------------------------------- pending sign-ins (state)


@dataclass
class PendingLogin:
    provider_id: int
    nonce: str
    code_verifier: str
    redirect_uri: str
    return_to: str
    created_at: float


class _StateStore:
    """Pending sign-ins for 10 minutes: Redis when sessions are in Redis, memory otherwise. Read once."""

    def __init__(self) -> None:
        self._memory: dict[str, tuple[float, str]] = {}
        self._redis = None
        if str(settings.SESSION_STORE_BACKEND or "").lower() == "redis":
            import redis

            self._redis = redis.Redis(
                host=settings.REDIS_HOST,
                port=int(settings.REDIS_PORT),
                db=int(settings.REDIS_DB),
                username=settings.REDIS_USERNAME,
                password=settings.REDIS_PASSWORD,
                ssl=bool(settings.REDIS_TLS),
                socket_timeout=float(settings.REDIS_TIMEOUT_SECONDS),
                decode_responses=True,
            )

    def _key(self, state: str) -> str:
        return f"{settings.REDIS_KEY_PREFIX}:oidc_state:{state}"

    def put(self, state: str, pending: PendingLogin) -> None:
        payload = json.dumps(pending.__dict__)
        if self._redis is not None:
            self._redis.set(self._key(state), payload, ex=STATE_TTL_SECONDS)
            return
        now = time.time()
        self._memory = {k: v for k, v in self._memory.items() if v[0] > now}
        self._memory[state] = (now + STATE_TTL_SECONDS, payload)

    def pop(self, state: str) -> PendingLogin | None:
        if self._redis is not None:
            payload = self._redis.getdel(self._key(state))
        else:
            expires, payload = self._memory.pop(state, (0.0, None))
            if expires < time.time():
                payload = None
        return PendingLogin(**json.loads(payload)) if payload else None


state_store = _StateStore()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


async def authorization_url(provider: dict[str, Any], *, redirect_uri: str, return_to: str) -> str:
    config = await discovery(provider)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    state_store.put(
        state,
        PendingLogin(
            provider_id=int(provider["id"]),
            nonce=nonce,
            code_verifier=verifier,
            redirect_uri=redirect_uri,
            return_to=return_to,
            created_at=time.time(),
        ),
    )
    params = {
        "response_type": "code",
        "client_id": provider["client_id"],
        "redirect_uri": redirect_uri,
        "scope": provider.get("scopes") or "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256",
    }
    return f"{config['authorization_endpoint']}?{urllib.parse.urlencode(params)}"


# ---------------------------------------------------------------- code exchange


def _jwt_payload(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError) as exc:
        raise OidcError("SSO_TOKEN_INVALID", "Malformed token from Keycloak") from exc


def claim_values(claims: dict[str, Any], path: str) -> list[str]:
    """Values at a dotted path (realm_access.roles, resource_access.<client>.roles, groups)."""
    node: Any = claims
    for part in [p for p in str(path or "").split(".") if p]:
        if not isinstance(node, dict):
            return []
        node = node.get(part)
    if isinstance(node, list):
        return [str(v) for v in node]
    return [str(node)] if isinstance(node, (str, int)) else []


async def exchange_code(provider: dict[str, Any], client_secret: str | None, pending: PendingLogin, *, code: str) -> dict[str, Any]:
    """Tokens for the code, ID token checked; returns the merged claims (ID token, access token, userinfo)."""
    config = await discovery(provider)
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": pending.redirect_uri,
        "client_id": provider["client_id"],
        "code_verifier": pending.code_verifier,
    }
    if client_secret:
        form["client_secret"] = client_secret
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=_verify(provider)) as client:
            resp = await client.post(config["token_endpoint"], data=form)
            if resp.status_code != 200:
                body = resp.json() if resp.content else {}
                error = str(body.get("error") or resp.status_code)
                if error == "invalid_client" or error == "unauthorized_client":
                    raise OidcError("SSO_CLIENT_REJECTED", "Keycloak refused the client ID or secret")
                raise OidcError("SSO_CODE_REJECTED", f"Keycloak refused the sign-in code ({error})")
            tokens = resp.json()
            userinfo: dict[str, Any] = {}
            if config.get("userinfo_endpoint") and tokens.get("access_token"):
                info = await client.get(config["userinfo_endpoint"], headers={"Authorization": f"Bearer {tokens['access_token']}"})
                if info.status_code == 200:
                    userinfo = info.json()
    except httpx.HTTPError as exc:
        raise OidcError("SSO_UNREACHABLE", f"Keycloak unreachable: {exc}") from exc

    id_claims = _jwt_payload(str(tokens.get("id_token") or ""))
    if id_claims.get("iss") != config["issuer"]:
        raise OidcError("SSO_TOKEN_INVALID", "ID token from another issuer")
    audience = id_claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if provider["client_id"] not in audiences:
        raise OidcError("SSO_TOKEN_INVALID", "ID token issued for another client")
    if float(id_claims.get("exp") or 0) < time.time() - 30:
        raise OidcError("SSO_TOKEN_INVALID", "ID token expired")
    if id_claims.get("nonce") != pending.nonce:
        raise OidcError("SSO_TOKEN_INVALID", "ID token nonce mismatch (replayed sign-in)")
    access_claims = _jwt_payload(tokens["access_token"]) if str(tokens.get("access_token") or "").count(".") == 2 else {}
    if userinfo and userinfo.get("sub") not in (None, id_claims.get("sub")):
        raise OidcError("SSO_TOKEN_INVALID", "Userinfo for another user")
    return {**access_claims, **id_claims, **userinfo}


async def test_provider(provider: dict[str, Any], client_secret: str | None) -> dict[str, Any]:
    """Discovery, then the client credentials: a dummy code is refused with invalid_grant when the client is right."""
    config = await discovery(provider, fresh=True)
    form = {"grant_type": "authorization_code", "code": "b2s-connection-test", "redirect_uri": "https://invalid.example/", "client_id": provider["client_id"]}
    if client_secret:
        form["client_secret"] = client_secret
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=_verify(provider)) as client:
            resp = await client.post(config["token_endpoint"], data=form)
    except httpx.HTTPError as exc:
        raise OidcError("SSO_UNREACHABLE", f"Token endpoint unreachable: {exc}") from exc
    error = str((resp.json() if resp.content else {}).get("error") or "")
    if error in {"invalid_client", "unauthorized_client"}:
        raise OidcError("SSO_CLIENT_REJECTED", "Keycloak refused the client ID or secret (check them, and “Client authentication” on the client)")
    return {
        "issuer": config["issuer"],
        "authorization_endpoint": config["authorization_endpoint"],
        "token_endpoint": config["token_endpoint"],
        "end_session_endpoint": config.get("end_session_endpoint"),
        "client_check": error or "accepted",
    }
