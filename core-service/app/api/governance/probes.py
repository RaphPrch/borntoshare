from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schemas.api_envelopes import data_envelope
from app.services.probe_service import fetch_probe_job, submit_probe_run


router = APIRouter(prefix="/probes", tags=["probes"])


class ProbeRunRequest(BaseModel):
    kind: str = Field(..., min_length=1)
    protocol: str = Field(..., min_length=1)
    scope: str | None = None

    target: dict[str, Any] = Field(default_factory=dict)
    auth: dict[str, Any] | None = None
    options: dict[str, Any] | None = None
    context: dict[str, Any] | None = None


@router.post("/run")
async def run_probe(payload: ProbeRunRequest) -> dict[str, Any]:
    data = await submit_probe_run(payload.model_dump())
    return data_envelope(data)


@router.get("/jobs/{job_id}")
async def get_probe_job(job_id: str) -> dict[str, Any]:
    data = await fetch_probe_job(job_id)
    return data_envelope(data)

