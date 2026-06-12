from __future__ import annotations

from typing import Any, Dict, Iterable
import httpx

from app.core import settings


class SecretResolveError(RuntimeError):
    def __init__(self, *, code: str, message: str, ref: str, http_status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.ref = ref
        self.http_status = http_status


def _client() -> httpx.Client:
    return httpx.Client(timeout=5.0)


def _internal_headers() -> Dict[str, str]:
    if not settings.INTERNAL_TOKEN:
        return {}
    return {"X-Internal-Token": settings.INTERNAL_TOKEN}


def resolve_secret_refs(secret_refs: Iterable[str]) -> Dict[str, str]:
    """Resolve secret references to values via secret-broker (v1)."""
    refs = [r for r in (secret_refs or []) if r]
    if not refs:
        return {}

    headers = _internal_headers()
    if not headers:
        raise RuntimeError("Missing internal token for secret-broker calls")

    out: Dict[str, str] = {}
    with _client() as client:
        for ref in refs:
            resp = client.post(f"{settings.SECRET_BROKER_URL}/resolve", json={"ref": ref}, headers=headers)
            if resp.status_code != 200:
                code = "SECRET_PROVIDER_FAILURE"
                message = f"Secret broker error for {ref}"
                try:
                    payload: Dict[str, Any] = resp.json() if resp.content else {}
                    error = payload.get("error") if isinstance(payload, dict) else None
                    if isinstance(error, dict):
                        code = str(error.get("code") or code)
                        message = str(error.get("message") or message)
                except Exception:
                    pass
                raise SecretResolveError(code=code, message=message, ref=ref, http_status=resp.status_code)
            data: Dict[str, Any] = resp.json()
            payload = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
            val = (payload or {}).get("value")
            if val is None:
                raise SecretResolveError(
                    code="SECRET_PROVIDER_FAILURE",
                    message=f"Secret broker invalid response for {ref}",
                    ref=ref,
                    http_status=500,
                )
            out[ref] = str(val)
    return out


def materialize_secrets_for_runner(resolved: Dict[str, str]) -> Dict[str, Any]:
    """Build the Runner v1 secrets payload from resolved secret values."""
    items: Dict[str, Any] = {}
    for k, v in (resolved or {}).items():
        items[k] = {"value": v}
    return {"items": items}
