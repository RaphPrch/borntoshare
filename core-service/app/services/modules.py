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
