"""Read-only access to the secret broker for core-service.

core-service resolves a single kind of secret: the password of a worker's agent, needed to check the
worker itself (a worker cannot report that it is down). Every other secret is resolved by the workers
or by auth-service, never here.
"""
from __future__ import annotations

import os

import httpx


class SecretUnavailable(RuntimeError):
    pass


def _broker_url() -> str:
    return (os.getenv("B2S_SECRET_BROKER_URL", "http://secret-broker:8010") or "").rstrip("/")


async def resolve_worker_password(ref: str) -> str:
    token = (os.getenv("INTERNAL_TOKEN") or "").strip()
    if not token:
        raise SecretUnavailable("INTERNAL_TOKEN is required to read the password of a worker")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{_broker_url()}/resolve", json={"ref": ref}, headers={"X-Internal-Token": token})
    except httpx.HTTPError as exc:
        raise SecretUnavailable(f"Secret broker unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise SecretUnavailable(f"Secret broker refused the password of the worker (HTTP {resp.status_code})")
    data = resp.json() if resp.content else {}
    payload = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
    value = (payload or {}).get("value")
    if value is None:
        raise SecretUnavailable("Secret broker returned no value")
    return str(value)
