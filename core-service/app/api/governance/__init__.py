"""Orchestration routes, mounted under /api/governance.

They turn user intents (access requests, identity imports, probes, AD groups)
into provisioning jobs published to Dramatiq for capsule-runner.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.governance.access_requests import router as access_requests_router
from app.api.governance.audit import router as audit_router
from app.api.governance.identity_orchestration import router as identity_orchestration_router
from app.api.governance.probes import router as probes_router
from app.api.governance.provisioning import router as provisioning_router
from app.core.internal_auth import require_orchestration_access

router = APIRouter(prefix="/governance", dependencies=[Depends(require_orchestration_access)])
router.include_router(probes_router)
router.include_router(provisioning_router)
router.include_router(identity_orchestration_router)
router.include_router(audit_router)
router.include_router(access_requests_router)
