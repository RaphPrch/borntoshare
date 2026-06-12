from __future__ import annotations

import logging
from typing import Any

import dramatiq
from dramatiq.middleware import CurrentMessage

from app.core.job_dispatcher import run_job as dispatch_job
from app.jobs.broker import broker as _broker  # noqa: F401
from app.shared.b2s_job_contracts.contracts import (
    QUEUE_ACL,
    QUEUE_IDENTITY,
    QUEUE_PROBES,
    QUEUE_PROVISIONING,
)


logger = logging.getLogger("capsule-runner.actor")

def _dispatch(job_id: int) -> None:
    numeric_job_id = int(job_id)
    current = CurrentMessage.get_current_message()
    retries = int(getattr(current, "options", {}).get("retries", 0) or 0) if current else 0
    max_retries = int(getattr(current, "options", {}).get("max_retries", 5) or 5) if current else 5
    dispatch_job(numeric_job_id, retries=retries, max_retries=max_retries)


@dramatiq.actor(queue_name=QUEUE_IDENTITY, max_retries=5)
def run_identity_job(job_id: int) -> None:
    _dispatch(job_id)


@dramatiq.actor(queue_name=QUEUE_PROVISIONING, max_retries=5)
def run_provisioning_job(job_id: int) -> None:
    _dispatch(job_id)


@dramatiq.actor(queue_name=QUEUE_ACL, max_retries=5)
def run_acl_job(job_id: int) -> None:
    _dispatch(job_id)


@dramatiq.actor(queue_name=QUEUE_PROBES, max_retries=5)
def run_probe_job(job_id: int) -> None:
    _dispatch(job_id)
