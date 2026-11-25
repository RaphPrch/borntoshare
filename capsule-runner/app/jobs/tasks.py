"""Entry of the Dramatiq worker (python -m dramatiq app.jobs.tasks)."""
from __future__ import annotations

import logging

from app.core.log_format import ServiceFormatter, use_on
from app.shared.b2s_job_contracts.actors import (
    run_acl_job,
    run_identity_job,
    run_probe_job,
    run_provisioning_job,
    run_scan_job,
)

# The lines of the worker like those of the services: text, or JSON with LOG_FORMAT=json (Dramatiq set up the handler)
use_on(logging.getLogger(), ServiceFormatter("capsule-runner", "WORKER"))

__all__ = [
    "run_acl_job",
    "run_identity_job",
    "run_probe_job",
    "run_provisioning_job",
    "run_scan_job",
]
