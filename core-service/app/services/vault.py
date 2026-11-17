"""HashiCorp Vault as an external vault (Advanced settings › Extensions › Vault).

Any password field of BornToShare (directory, file server, SMTP, an extension token…) may hold a reference instead of
the password:  vault://<kv mount>/<path>#<key>   e.g.  vault://secret/borntoshare/svc-b2s-sync#password
The reference is kept in the internal store like a password (encrypted); when the value is needed, the core reads it in
Vault (KV version 2) with its own identity: a token, or an AppRole (role_id in the settings, secret_id as the secret
of the extension). The value is kept in memory VALUE_TTL seconds at most, never written.
"""
from __future__ import annotations

import threading
import time
from typing import Any
from urllib.parse import quote

import httpx

PREFIX = "vault://"
VALUE_TTL = 60
TIMEOUT = 8
_cache: dict[str, tuple[float, str]] = {}
_token: dict[str, Any] = {"value": None, "until": 0.0, "for": None}
_lock = threading.Lock()


class VaultError(RuntimeError):
    code = "VAULT_FAILED"


def is_reference(value: str | None) -> bool:
    return str(value or "").startswith(PREFIX)


def parse(reference: str) -> tuple[str, str, str]:
    """vault://mount/path/to/secret#key → (mount, path, key)."""
    body = str(reference)[len(PREFIX):]
    location, _, key = body.partition("#")
    parts = [part for part in location.split("/") if part]
    if len(parts) < 2 or not key or ".." in parts:
        raise VaultError("Référence Vault invalide : vault://<montage>/<chemin>#<clé>")
    return parts[0], "/".join(parts[1:]), key


def _verify(config: dict[str, Any]) -> bool | str:
    mode = str(config.get("verify") or "public")
    if mode == "none":
        return False
    if mode == "file":
        return "/etc/b2s/certs/vault-ca.pem"
    return True


def _headers(config: dict[str, Any], token: str | None = None) -> dict[str, str]:
    headers = {"X-Vault-Request": "true"}
    if token:
        headers["X-Vault-Token"] = token
    if config.get("namespace"):
        headers["X-Vault-Namespace"] = str(config["namespace"])
    return headers


def _base(config: dict[str, Any]) -> str:
    url = str(config.get("url") or "").rstrip("/")
    if not url:
        raise VaultError("Adresse de Vault absente")
    return url


def token_for(config: dict[str, Any], secret: str | None) -> str:
    """The token of the core: the one given (auth « token »), or a login with the AppRole, kept until near its end."""
    if str(config.get("auth") or "token") == "token":
        if not secret:
            raise VaultError("Jeton Vault absent")
        return secret
    who = (config.get("url"), config.get("role_id"))
    with _lock:
        if _token["value"] and _token["for"] == who and time.monotonic() < _token["until"]:
            return str(_token["value"])
    mount = str(config.get("approle_mount") or "approle").strip("/")
    response = httpx.post(f"{_base(config)}/v1/auth/{mount}/login", json={"role_id": config.get("role_id"), "secret_id": secret},
                          headers=_headers(config), timeout=TIMEOUT, verify=_verify(config))
    if response.status_code >= 300:
        raise VaultError(f"Connexion AppRole refusée (HTTP {response.status_code})")
    auth = response.json().get("auth") or {}
    lease = int(auth.get("lease_duration") or 300)
    with _lock:
        _token.update(value=auth.get("client_token"), until=time.monotonic() + max(30, lease * 0.8), **{"for": who})
    return str(auth.get("client_token"))


def read(config: dict[str, Any], secret: str | None, reference: str) -> str:
    """The value a reference points to (KV v2), kept VALUE_TTL seconds in memory."""
    cached = _cache.get(reference)
    if cached and time.monotonic() < cached[0]:
        return cached[1]
    mount, path, key = parse(reference)
    url = f"{_base(config)}/v1/{quote(mount)}/data/{'/'.join(quote(part) for part in path.split('/'))}"
    response = httpx.get(url, headers=_headers(config, token_for(config, secret)), timeout=TIMEOUT, verify=_verify(config))
    if response.status_code == 404:
        raise VaultError(f"Secret absent de Vault : {mount}/{path}")
    if response.status_code == 403:
        raise VaultError(f"Lecture refusée par Vault (politique) : {mount}/{path}")
    if response.status_code >= 300:
        raise VaultError(f"Vault a répondu HTTP {response.status_code} pour {mount}/{path}")
    data = ((response.json().get("data") or {}).get("data") or {})
    if key not in data:
        raise VaultError(f"Clé « {key} » absente du secret {mount}/{path}")
    value = str(data[key])
    _cache[reference] = (time.monotonic() + VALUE_TTL, value)
    return value


def check(config: dict[str, Any], secret: str | None) -> dict[str, Any]:
    """Vault reachable and unsealed, the identity of the core accepted, and (when given) the test reference readable."""
    health = httpx.get(f"{_base(config)}/v1/sys/health", headers=_headers(config), timeout=TIMEOUT, verify=_verify(config))
    state = health.json() if health.headers.get("content-type", "").startswith("application/json") else {}
    if state.get("sealed"):
        raise VaultError("Vault est scellé (sealed)")
    token = token_for(config, secret)
    look = httpx.get(f"{_base(config)}/v1/auth/token/lookup-self", headers=_headers(config, token), timeout=TIMEOUT, verify=_verify(config))
    if look.status_code >= 300:
        raise VaultError(f"Identité refusée par Vault (HTTP {look.status_code})")
    out = {"version": state.get("version"), "policies": (look.json().get("data") or {}).get("policies")}
    if config.get("test_reference"):
        read(config, secret, str(config["test_reference"]))
        out["test_reference"] = "lisible"
    return out


def forget() -> None:
    _cache.clear()
    _token.update(value=None, until=0.0)
    _token["for"] = None
