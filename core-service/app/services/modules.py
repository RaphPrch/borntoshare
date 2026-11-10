"""The optional modules running in their own containers, seen from the core.

fives-service (5S and data hygiene) receives each measure of a folder: one more point of its history and the
fingerprints of the biggest files (its own databases). Only while the module is licensed and switched on; a module
that does not answer never makes the measure fail (it catches up at the next one)."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger("core.modules")


def fives_url() -> str:
    return os.getenv("B2S_FIVES_URL", "").strip().rstrip("/")


# Is the module installed (its container answers and reaches its tables)? Asked at most every 30 s (10 s when not)
_installed: dict[str, Any] = {"at": 0.0, "value": False}


def fives_installed() -> bool:
    import time

    now = time.monotonic()
    if now - _installed["at"] < (30 if _installed["value"] else 10):
        return bool(_installed["value"])
    url = fives_url()
    value = False
    if url:
        try:
            response = httpx.get(f"{url}/health", timeout=2)
            value = response.status_code == 200 and response.json().get("schema") is True
        except (httpx.HTTPError, ValueError):
            value = False
    _installed.update(at=now, value=value)
    return value


def push_measure(db: Session, storage_root_id: int, *, measured_at: datetime, bytes_: int, stats: dict[str, Any],
                 fingerprints: list[dict[str, Any]]) -> bool:
    from app.services import features

    url = fives_url()
    if not url or not features.enabled(db, "fives"):
        return False
    body = {"storage_root_id": int(storage_root_id), "measured_at": measured_at.isoformat() + "Z", "bytes": int(bytes_),
            "stats": {key: value for key, value in stats.items() if key != "fingerprints"}, "fingerprints": fingerprints[:500]}
    try:
        response = httpx.post(f"{url}/internal/measures", json=body, headers={"x-internal-token": os.getenv("INTERNAL_TOKEN", "")}, timeout=10)
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.warning("FIVES_MEASURE_NOT_SENT", extra={"storage_root_id": storage_root_id}, exc_info=True)
        return False


def request_scan(db: Session, storage_root_id: int, *, reason: str, by: str | None) -> bool:
    """Ask the scanner of the 5S module to measure the folder (False: the module does not answer)."""
    from sqlalchemy import text

    url = fives_url()
    if not url:
        return False
    row = db.execute(text("SELECT root_path FROM storage_roots WHERE id = :id"), {"id": int(storage_root_id)}).first()
    body = {"roots": [{"storage_root_id": int(storage_root_id), "root_path": row[0] if row else ""}], "reason": reason, "by": by}
    try:
        response = httpx.post(f"{url}/internal/scans", json=body, headers={"x-internal-token": os.getenv("INTERNAL_TOKEN", "")}, timeout=10)
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.warning("FIVES_SCAN_NOT_REQUESTED", extra={"storage_root_id": storage_root_id}, exc_info=True)
        return False
