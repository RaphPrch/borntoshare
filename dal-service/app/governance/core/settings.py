from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    # --------------------------------------------------
    # Core
    # --------------------------------------------------
    env: str
    allow_public_api: bool

    # --------------------------------------------------
    # Internal auth (service-to-service)
    # --------------------------------------------------
    # Token mode:
    # - "static" : compare X-Internal-Token with INTERNAL_TOKEN (dev only)
    # - "hmac"   : short-lived signed tokens (rotation via multiple keys)
    internal_token_mode: str
    internal_token: str | None
    internal_token_keys: str
    internal_token_ttl_sec: int

    # --------------------------------------------------
    # Broker (Dramatiq)
    # --------------------------------------------------
    capsule_broker_url: str

    # --------------------------------------------------
    # Jobs watchdog
    # --------------------------------------------------
    job_watchdog_enabled: bool
    job_watchdog_interval_seconds: int
    job_watchdog_queued_timeout_seconds: int
    job_watchdog_max_republish: int
    job_watchdog_limit: int


@lru_cache
def get_settings() -> Settings:
    env = os.getenv("APP_ENV", os.getenv("ENV", "dev"))
    allow_public_api = os.getenv("B2S_ALLOW_PUBLIC_API", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    # --------------------------------------------------
    # Internal token configuration (CRITICAL)
    # --------------------------------------------------
    internal_token_mode = os.getenv("INTERNAL_TOKEN_MODE", "hmac").strip().lower()

    # ⚠️ IMPORTANT:
    # DO NOT provide a default value here.
    # INTERNAL_TOKEN must be UNSET when mode=hmac
    internal_token = os.getenv("INTERNAL_TOKEN")

    # Format: "kid1:secret1,kid2:secret2" (rotation = add new kid, keep old for a while)
    internal_token_keys = os.getenv("INTERNAL_TOKEN_KEYS", "").strip()
    internal_token_ttl_sec = int(os.getenv("INTERNAL_TOKEN_TTL_SEC", "300"))

    capsule_broker_url = os.getenv("CAPSULE_BROKER_URL", "").strip()
    if not capsule_broker_url:
        raise RuntimeError("CAPSULE_BROKER_URL is required")

    job_watchdog_enabled = os.getenv("JOB_WATCHDOG_ENABLED", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    job_watchdog_interval_seconds = max(15, int(os.getenv("JOB_WATCHDOG_INTERVAL_SECONDS", "30")))
    job_watchdog_queued_timeout_seconds = max(30, int(os.getenv("JOB_WATCHDOG_QUEUED_TIMEOUT_SECONDS", "300")))
    job_watchdog_max_republish = max(0, int(os.getenv("JOB_WATCHDOG_MAX_REPUBLISH", "1")))
    job_watchdog_limit = max(1, min(int(os.getenv("JOB_WATCHDOG_LIMIT", "200")), 1000))

    return Settings(
        env=env,
        allow_public_api=allow_public_api,
        internal_token_mode=internal_token_mode,
        internal_token=internal_token,
        internal_token_keys=internal_token_keys,
        internal_token_ttl_sec=internal_token_ttl_sec,
        capsule_broker_url=capsule_broker_url,
        job_watchdog_enabled=job_watchdog_enabled,
        job_watchdog_interval_seconds=job_watchdog_interval_seconds,
        job_watchdog_queued_timeout_seconds=job_watchdog_queued_timeout_seconds,
        job_watchdog_max_republish=job_watchdog_max_republish,
        job_watchdog_limit=job_watchdog_limit,
    )
