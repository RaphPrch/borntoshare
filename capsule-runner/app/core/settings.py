# capsule-runner/settings.py
from __future__ import annotations

import os


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


# ==========================================================
# 🔐 Secret Broker (V1)
# ==========================================================
SECRET_BROKER_URL: str = (_env("B2S_SECRET_BROKER_URL", "http://secret-broker:8010") or "").rstrip("/")
INTERNAL_TOKEN: str | None = (_env("INTERNAL_TOKEN") or None)


# ==========================================================
# 🧠 Execution scope (V1)
# ==========================================================
# Allowed values: read | write | admin
RUNNER_MAX_SCOPE: str = (_env("RUNNER_MAX_SCOPE", "write") or "write").lower()

if RUNNER_MAX_SCOPE not in {"read", "write", "admin"}:
    raise RuntimeError(
        f"Invalid RUNNER_MAX_SCOPE: {RUNNER_MAX_SCOPE} (expected read|write|admin)"
    )


# ==========================================================
# 🗄️ DAL + broker (Dramatiq)
# ==========================================================
DAL_URL: str = (_env("DAL_URL", "http://dal-service:8000") or "").rstrip("/")
CAPSULE_BROKER_URL: str = (_env("CAPSULE_BROKER_URL") or "").strip()

if not CAPSULE_BROKER_URL:
    raise RuntimeError("CAPSULE_BROKER_URL is required")
