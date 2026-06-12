from __future__ import annotations

from fastapi import FastAPI
import logging
import os

from app.core import settings
from app.core.api_envelope import ok_data

raw_level = os.getenv("LOG_LEVEL", "INFO").upper()
level = getattr(logging, raw_level, logging.INFO)

logging.basicConfig(
    level=level,
    format="%(asctime)s [%(levelname)s] [RUNNER] %(name)s - %(message)s",
)
logging.getLogger().setLevel(level)

logger = logging.getLogger("capsule-runner")


app = FastAPI(
    title="BornToShare Capsule Runner",
    version="v1",
    description=(
        "BornToShare Capsule Runner worker runtime (Community v1).\n\n"
        "This service executes jobs from queue as a Dramatiq worker. "
        "HTTP surface is intentionally limited to health checks."
    ),
)


@app.get("/health")
def health():
    return ok_data({"status": "ok", "max_scope": settings.RUNNER_MAX_SCOPE, "version": "v1"})
