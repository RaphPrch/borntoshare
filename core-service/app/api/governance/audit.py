from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.schemas.api_envelopes import data_envelope
from app.services.audit_logger import log_event

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventIn(BaseModel):
    action: str = Field(..., min_length=1, max_length=128)
    event_category: str | None = Field(default=None, max_length=32)
    event_scope: str = Field(default="business", min_length=1, max_length=16)
    actor_type: str = Field(default="system", min_length=1, max_length=16)
    actor_id: int | str | None = None
    entity_type: str = Field(default="request", min_length=1, max_length=80)
    entity_id: int | str | None = None
    zone_id: int | None = None
    storage_root_id: int | None = None
    correlation_id: str | None = Field(default=None, max_length=128)
    result: str = Field(default="success", min_length=1, max_length=20)
    severity: str = Field(default="info", min_length=1, max_length=20)
    metadata_json: dict[str, Any] | None = None


def _infer_category(entity_type: str | None, action: str) -> str:
    et = str(entity_type or "").lower()
    a = str(action or "").lower()
    if "storage_root" in et or "storage_root" in a:
        return "STORAGE_ROOT"
    if "access_profile" in et or "access_profile" in a:
        return "ACCESS_PROFILE"
    if "policy" in et or "policy" in a:
        return "POLICY"
    if "member" in a or "subject" in a:
        return "MEMBER"
    return "PROVISIONING"


def _canonical_action(action: str) -> str:
    raw = str(action or "").strip().lower().replace(".", "_")
    aliases = {
        "storage_root_created": "storage_root.created",
        "storage_root_updated": "storage_root.updated",
        "storage_root_deleted": "storage_root.deleted",
        "access_profile_created": "access_profile_created",
        "access_profile_deleted": "access_profile_deleted",
        "access_profile_provisioning_started": "access_profile_provisioning_started",
        "access_profile_provisioning_succeeded": "access_profile_provisioning_succeeded",
        "access_profile_provisioning_failed": "access_profile_provisioning_failed",
        "member_added": "member_added",
        "member_removed": "member_removed",
        "access_policy_updated": "access_policy_updated",
        "access_profile_subject_added": "member_added",
        "access_profile_subject_removed": "member_removed",
    }
    return aliases.get(raw, raw)


@router.post("/events")
async def create_audit_event(payload: AuditEventIn, request: Request):
    actor_id = payload.actor_id
    if actor_id is None:
        actor_id = request.headers.get("x-identity-id") or request.headers.get("x-service-name") or "system"

    entity_type = payload.entity_type or "request"
    entity_id = payload.entity_id

    corr = (
        payload.correlation_id
        or request.headers.get("x-request-id")
        or request.headers.get("x-correlation-id")
    )
    canonical_action = _canonical_action(payload.action)
    category = payload.event_category or _infer_category(entity_type, canonical_action)
    result = payload.result if payload.result else "success"

    log_event(
        action=canonical_action,
        event_category=category,
        event_scope=payload.event_scope,
        actor_type=payload.actor_type,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        zone_id=payload.zone_id,
        storage_root_id=payload.storage_root_id,
        correlation_id=corr,
        result=result,
        severity=payload.severity,
        metadata_json=payload.metadata_json,
    )
    return data_envelope({"ok": True})
