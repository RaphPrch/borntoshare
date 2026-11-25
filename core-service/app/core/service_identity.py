"""Who calls core-service, and for whom (H4 of the V1 qualification).

Callers: each service has its own token (X-Service-Token), core-service knows them all (B2S_TOKEN_<SERVICE>, from
podman secrets). The caller is the service whose token matches, never a name it declares; what it may do is set
here, never announced by it:
  - frontend (the BFF): acts for a person only, never as an « internal » service;
  - auth: the authentication service, trusted for the internal routes;
  - capsule (the worker) and fives (the 5S module): only the routes they need (PATH_ALLOWED).

The person: an assertion signed by the BFF or auth-service with PRINCIPAL_SIGNING_KEY (X-B2S-Actor: identity,
roles, name, expiry 60 s, audience « core »). The worker and the 5S module do not hold the key: they cannot claim
to be someone; the 5S module relays the assertion it received, untouched.

Until make deploy has given the tokens (an installation from before), the shared INTERNAL_TOKEN and the identity
headers are still accepted (« legacy » mode): Health › Diagnostic says so.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

SERVICES = ("frontend", "auth", "capsule", "fives")
ACTOR_HEADER = "x-b2s-actor"
TOKEN_HEADER = "x-service-token"
ACTOR_AUDIENCE = "core"
ACTOR_TTL_SECONDS = 60

# What a narrow service may call (method, prefix); auth and frontend are not listed: not restricted by path
PATH_ALLOWED: dict[str, tuple[tuple[str | None, str], ...]] = {
    "capsule": (
        (None, "/api/internal/provisioning/"),
        (None, "/api/internal/secrets/resolve"),
        (None, "/api/internal/network/dns"),
        ("GET", "/api/admin/config/advanced"),  # its log level, read at start
    ),
    "fives": (
        (None, "/api/internal/modules/fives/"),
        (None, "/api/internal/secrets/resolve"),
        (None, "/api/internal/network/dns"),
    ),
}

# Scopes of the scoped internal routes (require_internal), by caller
SCOPES: dict[str, frozenset[str]] = {
    "capsule": frozenset({"jobs:read", "jobs:write", "events:write", "profiles:write"}),
    "auth": frozenset({"jobs:read"}),
    "fives": frozenset(),
    "frontend": frozenset(),
}

# Callers that are « internal services » (the routes open to an administrator or to a service)
INTERNAL_CALLERS = frozenset({"auth", "capsule", "fives", "legacy"})


def service_tokens() -> dict[str, str]:
    """The token of each service, as core-service knows them (empty before make deploy gave them)."""
    out = {}
    for service in SERVICES:
        value = (os.getenv(f"B2S_TOKEN_{service.upper()}") or "").strip()
        if value:
            out[service] = value
    return out


def per_service_mode() -> bool:
    return bool(service_tokens())


def caller_of(service_token: str | None, internal_token: str | None) -> str | None:
    """The service whose token is given; « legacy » for the shared token before the tokens exist; None otherwise."""
    tokens = service_tokens()
    if tokens:
        provided = str(service_token or "").strip()
        if not provided:
            return None
        found = None
        for service, value in tokens.items():
            if hmac.compare_digest(provided, value):
                found = service
        return found
    expected = os.getenv("INTERNAL_TOKEN", "")
    provided = str(internal_token or "").strip()
    return "legacy" if expected and provided and hmac.compare_digest(provided, expected) else None


def path_allowed(caller: str, method: str, path: str) -> bool:
    rules = PATH_ALLOWED.get(caller)
    if rules is None:
        return True
    return any((rule_method is None or rule_method == method.upper()) and path.startswith(prefix) for rule_method, prefix in rules)


# ---- the person: signed assertion -------------------------------------------------------------------------------

@dataclass(frozen=True)
class VerifiedActor:
    identity_id: int | None
    roles: frozenset[str]
    display_name: str | None


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _key() -> bytes:
    return (os.getenv("PRINCIPAL_SIGNING_KEY") or "").encode("utf-8")


def sign_actor(identity_id: int | None, roles: list[str], display_name: str | None, *, now: float | None = None,
               key: bytes | None = None) -> str:
    """The assertion a trusted caller attaches (the BFF and auth-service do it in their language; here for tests)."""
    payload = {"id": identity_id, "roles": sorted({str(r).strip().lower() for r in roles if str(r).strip()}),
               "name": display_name, "aud": ACTOR_AUDIENCE, "exp": int((now or time.time()) + ACTOR_TTL_SECONDS)}
    body = _b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signature = _b64(hmac.new(key if key is not None else _key(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_actor(assertion: str | None, *, now: float | None = None) -> VerifiedActor | None:
    """The person of a valid assertion (signature, audience, not expired); None otherwise."""
    key = _key()
    raw = str(assertion or "").strip()
    if not key or "." not in raw:
        return None
    body, signature = raw.rsplit(".", 1)
    expected = _b64(hmac.new(key, body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("aud") != ACTOR_AUDIENCE or int(payload.get("exp") or 0) < (now or time.time()):
        return None
    identity = payload.get("id")
    return VerifiedActor(
        identity_id=int(identity) if isinstance(identity, (int, str)) and str(identity).isdigit() else None,
        roles=frozenset(str(r).strip().lower() for r in payload.get("roles") or [] if str(r).strip()),
        display_name=str(payload.get("name") or "").strip() or None,
    )
