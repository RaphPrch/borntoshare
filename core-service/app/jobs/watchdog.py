"""Republishes provisioning jobs stuck in QUEUED (JOB_WATCHDOG_* settings)."""
from __future__ import annotations

import asyncio
import uuid

from app.core.config import get_settings

settings = get_settings()


async def _jobs_watchdog_loop() -> None:
    from app.api.governance.provisioning import run_queued_jobs_watchdog_once

    while True:
        await asyncio.sleep(settings.JOB_WATCHDOG_INTERVAL_SECONDS)
        correlation_id = f"jobwatchdog_{uuid.uuid4().hex}"
        try:
            await run_queued_jobs_watchdog_once(
                queued_timeout_seconds=settings.JOB_WATCHDOG_QUEUED_TIMEOUT_SECONDS,
                max_republish_count=settings.JOB_WATCHDOG_MAX_REPUBLISH,
                limit=settings.JOB_WATCHDOG_LIMIT,
                correlation_id=correlation_id,
            )
        except Exception:
            # Watchdog must never crash the service loop.
            continue


def start_jobs_watchdog() -> None:
    if settings.JOB_WATCHDOG_ENABLED:
        asyncio.create_task(_jobs_watchdog_loop())
