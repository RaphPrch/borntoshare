from __future__ import annotations

import base64
import hashlib
import httpx
from urllib.parse import urlencode

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.keycloak_state import kc_state_store
from app.core.providers.keycloak import fetch_userinfo, KeycloakProvider

settings = get_settings()
logger = get_logger(__name__)

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _b64url(digest)

def authorize_url(state: str, code_challenge: str) -> str:
    base = KeycloakProvider().base() + "/auth"
    params = {
        "client_id": settings.KEYCLOAK_CLIENT_ID,
        "response_type": "code",
        "scope": settings.KEYCLOAK_SCOPES,
        "redirect_uri": settings.KEYCLOAK_REDIRECT_URI,
        "state": state,
    }
    if settings.KEYCLOAK_PKCE_ENABLED:
        params["code_challenge_method"] = "S256"
        params["code_challenge"] = code_challenge
    return base + "?" + urlencode(params)

async def exchange_code_for_token(code: str, code_verifier: str) -> str:
    token_url = KeycloakProvider().base() + "/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.KEYCLOAK_CLIENT_ID,
        "code": code,
        "redirect_uri": settings.KEYCLOAK_REDIRECT_URI,
    }
    if settings.KEYCLOAK_PKCE_ENABLED:
        data["code_verifier"] = code_verifier
    if settings.KEYCLOAK_CLIENT_SECRET:
        data["client_secret"] = settings.KEYCLOAK_CLIENT_SECRET

    async with httpx.AsyncClient(verify=settings.KEYCLOAK_VERIFY_TLS, timeout=10) as client:
        r = await client.post(token_url, data=data, headers={"Content-Type":"application/x-www-form-urlencoded"})
    if r.status_code != 200:
        logger.warning("KC token exchange failed | status=%s | body=%s", r.status_code, r.text[:300])
        raise ValueError("Token exchange failed")

    payload = r.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise ValueError("Missing access_token")
    return access_token

async def handle_callback(code: str, state: str):
    st = kc_state_store.pop(state)
    if not st:
        raise ValueError("Invalid or expired state")

    access_token = await exchange_code_for_token(code, st.code_verifier)
    user = await fetch_userinfo(access_token)
    return user
