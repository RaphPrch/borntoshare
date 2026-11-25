"""Jobs nobody will finish (JOB_WATCHDOG_* settings): republishes those stuck in QUEUED, closes as failed those
RUNNING beyond the time limit of their worker (JOB_ABANDONED)."""
from __future__ import annotations

import asyncio
import uuid

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("core.jobs.watchdog")


async def _jobs_watchdog_loop() -> None:
    from app.api.governance.provisioning import close_abandoned_jobs_once, run_queued_jobs_watchdog_once

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
            # Never stops the loop; never silent either
            logger.exception("JOB_WATCHDOG_QUEUED_FAILED", extra={"correlation_id": correlation_id})
        try:
            await close_abandoned_jobs_once(
                grace_seconds=settings.JOB_WATCHDOG_RUNNING_GRACE_SECONDS,
                limit=settings.JOB_WATCHDOG_LIMIT,
                correlation_id=correlation_id,
            )
        except Exception:
            logger.exception("JOB_WATCHDOG_RUNNING_FAILED", extra={"correlation_id": correlation_id})


def start_jobs_watchdog() -> asyncio.Task | None:
    if settings.JOB_WATCHDOG_ENABLED:
        return asyncio.create_task(_jobs_watchdog_loop())
    return None
