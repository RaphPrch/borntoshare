from __future__ import annotations

from typing import Any

__all__ = ["run_provisioning_job"]


def __getattr__(name: str) -> Any:
    if name == "run_provisioning_job":
        from app.shared.b2s_job_contracts.actors import run_provisioning_job

        return run_provisioning_job
    raise AttributeError(name)
