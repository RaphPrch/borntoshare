from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import List


def _split_csv(v: str | None) -> List[str]:
    if not v:
        return []
    return [x.strip() for x in v.split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    # --------------------------------------------------
    # Core
    # --------------------------------------------------
    env: str
    cors_allow_origins: List[str]
    allow_public_api: bool

    # --------------------------------------------------
    # DAL
    # --------------------------------------------------
    dal_url: str

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
    # Audit toggle (runtime bridge removed)
    # --------------------------------------------------
    wizard_activity_enabled: bool
    wizard_activity_timeout_seconds: int

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

    # SECURITY: default to no CORS unless explicitly configured
    cors = _split_csv(os.getenv("CORS_ALLOW_ORIGINS")) or []

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

    dal_url = os.getenv("DAL_URL", "http://dal-service:8000").rstrip("/")

    capsule_broker_url = os.getenv("CAPSULE_BROKER_URL", "").strip()
    if not capsule_broker_url:
        raise RuntimeError("CAPSULE_BROKER_URL is required")

    wizard_activity_enabled = os.getenv("WIZARD_ACTIVITY_ENABLED", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    wizard_activity_timeout_seconds = int(os.getenv("WIZARD_ACTIVITY_TIMEOUT_SECONDS", "5"))

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
        cors_allow_origins=cors,
        allow_public_api=allow_public_api,
        dal_url=dal_url,
        internal_token_mode=internal_token_mode,
        internal_token=internal_token,
        internal_token_keys=internal_token_keys,
        internal_token_ttl_sec=internal_token_ttl_sec,
        capsule_broker_url=capsule_broker_url,
        wizard_activity_enabled=wizard_activity_enabled,
        wizard_activity_timeout_seconds=wizard_activity_timeout_seconds,
        job_watchdog_enabled=job_watchdog_enabled,
        job_watchdog_interval_seconds=job_watchdog_interval_seconds,
        job_watchdog_queued_timeout_seconds=job_watchdog_queued_timeout_seconds,
        job_watchdog_max_republish=job_watchdog_max_republish,
        job_watchdog_limit=job_watchdog_limit,
    )
