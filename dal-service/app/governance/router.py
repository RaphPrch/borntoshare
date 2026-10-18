"""Governance (orchestration) routes, mounted by dal-service under /api/governance.

Governance turns user intents (access requests, identity imports, probes, AD groups)
into provisioning jobs published to Dramatiq for capsule-runner.
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends

from app.governance.api.access_requests import router as access_requests_router
from app.governance.api.audit import router as audit_router
from app.governance.api.identity_orchestration import router as identity_orchestration_router
from app.governance.api.probes import router as probes_router
from app.governance.api.provisioning import router as provisioning_router
from app.governance.api.provisioning import run_queued_jobs_watchdog_once
from app.governance.core.internal_guard import require_internal_token
from app.governance.core.settings import get_settings

PREFIX = "/governance"

settings = get_settings()

router = APIRouter(prefix=PREFIX, dependencies=[Depends(require_internal_token)])
router.include_router(probes_router)
router.include_router(provisioning_router)
router.include_router(identity_orchestration_router)
router.include_router(audit_router)
router.include_router(access_requests_router)


async def _jobs_watchdog_loop() -> None:
    while True:
        await asyncio.sleep(max(5, int(settings.job_watchdog_interval_seconds)))
        correlation_id = f"jobwatchdog_{uuid.uuid4().hex}"
        try:
            await run_queued_jobs_watchdog_once(
                queued_timeout_seconds=int(settings.job_watchdog_queued_timeout_seconds),
                max_republish_count=int(settings.job_watchdog_max_republish),
                limit=int(settings.job_watchdog_limit),
                correlation_id=correlation_id,
            )
        except Exception:
            # Watchdog must never crash the service loop.
            continue


def start_jobs_watchdog() -> None:
    """Republish provisioning jobs stuck in QUEUED (see JOB_WATCHDOG_*)."""
    if bool(settings.job_watchdog_enabled):
        asyncio.create_task(_jobs_watchdog_loop())
