"""What the scanner asks the core (internal API, shared token): where a folder is and with which account, the
password of that account (secret broker, never stored), and where to send what it found."""
from __future__ import annotations

from typing import Any

import httpx

from scanner import config


def _call(method: str, path: str, body: dict | None = None, timeout: float = 30) -> Any:
    response = httpx.request(method, f"{config.CORE_URL}{path}", json=body, timeout=timeout,
                             headers={"x-internal-token": config.INTERNAL_TOKEN, "x-service-name": "fives-scanner"})
    response.raise_for_status()
    data = response.json()
    return data.get("data", data) if isinstance(data, dict) else data


def context(storage_root_id: int) -> dict[str, Any]:
    return _call("GET", f"/api/internal/modules/fives/scan-context/{int(storage_root_id)}")


def password(secret_ref: str) -> str:
    value = (_call("POST", "/api/internal/secrets/resolve", {"ref": secret_ref}) or {}).get("value")
    if not value:
        raise RuntimeError("The account of the file server has no password in the secret broker")
    return str(value)


def report(storage_root_id: int, **fields: Any) -> None:
    """State of the measure for the folder page (running with progress, done with the content, failed)."""
    _call("POST", "/api/internal/modules/fives/measure-result", {"storage_root_id": int(storage_root_id), **fields}, timeout=60)


def delegate(storage_root_id: int, reason: str) -> None:
    """The server cannot be walked on (no WinRM, a DFS namespace…): the worker of the core measures it through SMB."""
    _call("POST", "/api/internal/modules/fives/delegate-measure", {"storage_root_id": int(storage_root_id), "reason": reason})
