from __future__ import annotations

import asyncio
from datetime import datetime
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.db import get_db
from app.core.logging import get_logger, log_event
from app.routers._helpers import ui_action, ui_data, ui_list
from app.schemas.access_request import AccessRequestCreate
from app.repositories.access_requests_repo import AccessRequestsRepo
from app.repositories.access_requests_views_repo import AccessRequestsViewsRepo
from app.repositories.storage_roots_views_repo import StorageRootsViewsRepo
from app.security.internal_auth import require_internal
from app.services.activity_log import log_activity
from app.services.authorization import (
    actor_from_request,
    filter_access_request_rows,
    is_platform_administrator,
    require_access_request_access,
    require_access_request_review,
)
from app.services.governance_proxy import gov_post
from app.services.naming_policy import resolve_group_name
from app.services.storage_root_access_profile_resolution import normalize_requested_permission


class BulkDecisionPayload(BaseModel):
    ids: list[int]
    decision: str
    decision_comment: str | None = None


class InternalItemExecutionPayload(BaseModel):
    access_request_id: int
    access_request_item_id: int | None = None
    status: str
    requested_payload_json: dict[str, Any]
    result_json: dict[str, Any] | None = None
    error_message: str | None = None


class ExistingAccessCheckPayload(BaseModel):
    storage_root_id: int
    permission: str | None = None
    access_level: str | None = None
    requester_identity_id: int | None = None
    requested_principal: dict[str, Any] | None = None


router = APIRouter(
    prefix="/access-requests",
    tags=["access_requests"],
)
logger = get_logger(__name__)

internal_router = APIRouter(
    prefix="/internal/access-requests",
    tags=["internal-access-requests"],
)


def _actor_from_headers(request: Request) -> tuple[int | None, str | None]:
    actor = actor_from_request(request)
    return actor.identity_id, actor.display_name


def _normalize_access_level_from_permission(value: str | None) -> str:
    return normalize_requested_permission(value) or "READ"


def _resolve_implicit_governed_group(
    *,
    db: Session,
    storage_root_id: int,
    requested_permission: str | None,
    target_type: str,
) -> dict[str, Any]:
    normalized_target = str(target_type or "").strip().lower()
    if normalized_target != "storage_root":
        return {
            "status": "unsupported_target_type",
            "error": {
                "code": "UNSUPPORTED_TARGET_TYPE",
                "message": "Only storage_root target type is supported for approval provisioning.",
                "hint": "Submit a request targeting a storage_root.",
                "storage_root_id": int(storage_root_id or 0) or None,
                "requested_permission": str(requested_permission or "").strip().upper() or None,
                "candidates_count": 0,
            },
        }

    access_level_code = normalize_requested_permission(requested_permission)
    if access_level_code not in {"READ", "WRITE"}:
        return {
            "status": "invalid_access_level",
            "error": {
                "code": "INVALID_ACCESS_LEVEL",
                "message": f"Requested access level '{str(requested_permission or '').strip()}' is not supported.",
                "hint": "Use READ or WRITE permission values.",
                "storage_root_id": int(storage_root_id or 0) or None,
                "requested_permission": str(requested_permission or "").strip().upper() or None,
                "candidates_count": 0,
            },
        }

    row = db.execute(
        text(
            """
            SELECT
              sr.id AS storage_root_id,
              sr.root_path,
              sr.name AS storage_root_name,
              se.zone_id,
              se.identity_source_id
            FROM storage_roots sr
            JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            WHERE sr.id = :storage_root_id
            LIMIT 1
            """
        ),
        {"storage_root_id": int(storage_root_id)},
    ).mappings().first()

    if not row:
        return {
            "status": "storage_root_not_found",
            "error": {
                "code": "STORAGE_ROOT_NOT_FOUND",
                "message": "Storage root not found.",
                "hint": "Verify the requested storage root still exists.",
                "storage_root_id": int(storage_root_id or 0) or None,
                "requested_permission": access_level_code,
                "candidates_count": 0,
            },
        }

    naming = resolve_group_name(
        db,
        zone_ref=int(row.get("zone_id") or 0) or None,
        storage_root_path=str(row.get("root_path") or row.get("storage_root_name") or "").strip(),
        perm="RW" if access_level_code == "WRITE" else "RX",
        profile=access_level_code,
    )
    group_ref = str((naming or {}).get("samAccountName") or "").strip()
    if not group_ref:
        return {
            "status": "group_name_missing",
            "error": {
                "code": "GOVERNED_GROUP_NAME_MISSING",
                "message": "Unable to resolve governed group name for this storage root.",
                "hint": "Check naming policy configuration for this zone/root.",
                "storage_root_id": int(storage_root_id or 0) or None,
                "requested_permission": access_level_code,
                "candidates_count": 0,
            },
        }

    return {
        "status": "GOVERNED_GROUP_RESOLVED_OR_CREATED",
        "access_level_code": access_level_code,
        "group_ref": group_ref,
        "group_name": group_ref,
        "identity_source_id": int(row.get("identity_source_id") or 0) or None,
    }


def _resolution_detail_to_message(*, item_id: int, detail: dict[str, Any] | None) -> str:
    payload = dict(detail or {})
    message = str(payload.get("message") or "").strip() or "approval blocked"
    return f"item#{int(item_id)}: {message}"


def _coerce_principal_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        raw = payload.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _principal_match_keys(
    *,
    identity_id: int | None,
    principal_dn: str | None,
    principal_username: str | None,
) -> set[str]:
    keys: set[str] = set()
    if int(identity_id or 0) > 0:
        keys.add(f"id:{int(identity_id)}")
    for value in (principal_dn, principal_username):
        text_value = str(value or "").strip().lower()
        if text_value:
            keys.add(f"text:{text_value}")
            if "\\" in text_value:
                short_value = text_value.split("\\")[-1]
                keys.add(f"text:{short_value}")
            if "@" in text_value:
                keys.add(f"text:{text_value.split('@', 1)[0]}")
    return keys


def _member_match_keys(member: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    identity_id = int(member.get("identity_id") or 0) if str(member.get("identity_id") or "").strip().isdigit() else 0
    if identity_id > 0:
        keys.add(f"id:{identity_id}")
    for field in ("dn", "external_id", "username", "upn", "email"):
        text_value = str(member.get(field) or "").strip().lower()
        if not text_value:
            continue
        keys.add(f"text:{text_value}")
        if "\\" in text_value:
            short_value = text_value.split("\\")[-1]
            keys.add(f"text:{short_value}")
        if "@" in text_value:
            keys.add(f"text:{text_value.split('@', 1)[0]}")
    return keys


def _current_access_level_for_principal(
    *,
    db: Session,
    storage_root_id: int,
    requested_principal_payload: Any,
    requester_identity_id: int | None,
) -> str:
    principal_dn, principal_username, _ = _resolve_request_principal(
        db=db,
        requested_principal_payload=requested_principal_payload,
        requester_identity_id=requester_identity_id,
    )
    principal_identity_id = _extract_principal_identity_id(requested_principal_payload)
    if not principal_identity_id:
        principal_identity_id = int(requester_identity_id or 0) or None
    wanted = _principal_match_keys(
        identity_id=principal_identity_id,
        principal_dn=principal_dn,
        principal_username=principal_username,
    )
    if not wanted:
        return "NONE"

    rows = StorageRootsViewsRepo(db)._build_acl_effective_access_rows(int(storage_root_id))
    current = "NONE"
    for row in rows:
        access_level = str(row.get("access_level") or "").strip().lower()
        if access_level not in {"read", "write"}:
            continue
        members = row.get("members") if isinstance(row.get("members"), list) else []
        if any(wanted.intersection(_member_match_keys(dict(member))) for member in members):
            if access_level == "write":
                return "WRITE"
            current = "READ"
    return current


def _find_open_request_for_principal(
    *,
    db: Session,
    storage_root_id: int,
    requested_principal_payload: Any,
    requester_identity_id: int | None,
) -> dict[str, Any] | None:
    principal_dn, principal_username, _ = _resolve_request_principal(
        db=db,
        requested_principal_payload=requested_principal_payload,
        requester_identity_id=requester_identity_id,
    )
    principal_identity_id = _extract_principal_identity_id(requested_principal_payload)
    if not principal_identity_id:
        principal_identity_id = int(requester_identity_id or 0) or None
    wanted = _principal_match_keys(
        identity_id=principal_identity_id,
        principal_dn=principal_dn,
        principal_username=principal_username,
    )
    if not wanted:
        return None

    rows = db.execute(
        text(
            """
            SELECT
              ar.id,
              ar.code,
              ar.requester_identity_id,
              ar.requested_principal_json
            FROM access_requests ar
            JOIN access_request_items ari ON ari.access_request_id = ar.id
            WHERE LOWER(COALESCE(ar.status, '')) = 'pending'
              AND LOWER(COALESCE(ari.target_type, '')) = 'storage_root'
              AND ari.target_id = :storage_root_id
            ORDER BY ar.id DESC
            """
        ),
        {"storage_root_id": int(storage_root_id)},
    ).mappings().all()

    for row in rows:
        existing_dn, existing_username, _ = _resolve_request_principal(
            db=db,
            requested_principal_payload=row.get("requested_principal_json"),
            requester_identity_id=int(row.get("requester_identity_id") or 0) or None,
        )
        existing_identity_id = _extract_principal_identity_id(row.get("requested_principal_json"))
        if not existing_identity_id:
            existing_identity_id = int(row.get("requester_identity_id") or 0) or None
        existing = _principal_match_keys(
            identity_id=existing_identity_id,
            principal_dn=existing_dn,
            principal_username=existing_username,
        )
        if wanted.intersection(existing):
            return dict(row)
    return None


def _evaluate_access_request_guardrails(
    *,
    db: Session,
    storage_root_id: int,
    requested_permission: str | None,
    requested_principal_payload: Any,
    requester_identity_id: int | None,
) -> dict[str, Any]:
    access_level = normalize_requested_permission(requested_permission)
    if access_level not in {"READ", "WRITE"}:
        return {
            "can_request": False,
            "current_access_level": "NONE",
            "code": "INVALID_ACCESS_LEVEL",
            "reason": "INVALID_ACCESS_LEVEL",
            "message": f"Niveau d'acces non supporte: {str(requested_permission or '').strip()}",
            "source": "UNKNOWN",
        }

    existing_request = _find_open_request_for_principal(
        db=db,
        storage_root_id=int(storage_root_id),
        requested_principal_payload=requested_principal_payload,
        requester_identity_id=requester_identity_id,
    )
    if existing_request:
        return {
            "can_request": False,
            "current_access_level": "NONE",
            "code": "ACCESS_REQUEST_ALREADY_EXISTS",
            "reason": "ACCESS_REQUEST_ALREADY_EXISTS",
            "message": "Une demande d'acces est deja en cours pour cet utilisateur et cette ressource.",
            "source": "DB",
            "access_request_id": int(existing_request.get("id") or 0) or None,
            "access_request_code": str(existing_request.get("code") or "").strip() or None,
        }

    current_access_level = _current_access_level_for_principal(
        db=db,
        storage_root_id=int(storage_root_id),
        requested_principal_payload=requested_principal_payload,
        requester_identity_id=requester_identity_id,
    )
    if current_access_level in {"READ", "WRITE"}:
        already_granted = current_access_level == "WRITE" or access_level == "READ"
        if already_granted:
            return {
                "can_request": False,
                "current_access_level": current_access_level,
                "code": "ACCESS_ALREADY_GRANTED",
                "reason": "ACCESS_ALREADY_GRANTED",
                "message": "L'utilisateur possede deja cet acces sur cette ressource.",
                "source": "EFFECTIVE_ACCESS",
            }
        return {
            "can_request": True,
            "current_access_level": current_access_level,
            "code": "ELEVATION_ALLOWED",
            "reason": "ELEVATION_ALLOWED",
            "message": "L'utilisateur possede deja un acces Lecture. Cette demande sera traitee comme une elevation vers Ecriture.",
            "source": "EFFECTIVE_ACCESS",
        }

    return {
        "can_request": True,
        "current_access_level": "NONE",
        "code": "NONE",
        "reason": "NONE",
        "message": "",
        "source": "EFFECTIVE_ACCESS",
    }


def _extract_principal_identity(payload: Any | None) -> tuple[str | None, str | None, str | None]:
    data = _coerce_principal_payload(payload)
    nested_payloads = [
        data.get("principal"),
        data.get("requested_principal"),
        data.get("subject"),
        data.get("identity"),
    ]
    nested = [item for item in nested_payloads if isinstance(item, dict)]

    def pick(*values: Any) -> str | None:
        for value in values:
            text_value = str(value or "").strip()
            if text_value:
                return text_value
        return None

    def values_for(*keys: str) -> list[Any]:
        values: list[Any] = [data.get(key) for key in keys]
        for item in nested:
            values.extend(item.get(key) for key in keys)
        return values

    principal_dn = pick(
        *values_for(
            "dn",
            "distinguishedName",
            "distinguished_name",
            "external_id",
            "externalId",
            "requested_principal_dn",
            "id",
            "identity_id",
        ),
    )
    principal_username = pick(
        *values_for(
            "username",
            "samaccountname",
            "sam_account_name",
            "samAccountName",
            "userPrincipalName",
            "user_principal_name",
            "upn",
            "email",
            "mail",
        ),
    )
    principal_display = pick(
        *values_for("display_name", "displayName", "name"),
        principal_username,
        principal_dn,
    )
    return principal_dn, principal_username, principal_display


def _extract_principal_identity_id(payload: Any | None) -> int | None:
    data = _coerce_principal_payload(payload)
    nested_payloads = [
        data.get("principal"),
        data.get("requested_principal"),
        data.get("subject"),
        data.get("identity"),
    ]
    nested = [item for item in nested_payloads if isinstance(item, dict)]

    candidates: list[Any] = [
        data.get("identity_id"),
        data.get("principal_id"),
        data.get("requested_identity_id"),
        data.get("subject_id"),
        data.get("id"),
    ]
    for item in nested:
        candidates.extend(
            [
                item.get("identity_id"),
                item.get("principal_id"),
                item.get("requested_identity_id"),
                item.get("subject_id"),
                item.get("id"),
            ]
        )

    for value in candidates:
        text_value = str(value or "").strip()
        if text_value.isdigit():
            parsed = int(text_value)
            if parsed > 0:
                return parsed
    return None


def _resolve_principal_from_identity_id(
    *,
    db: Session,
    identity_id: int | None,
) -> tuple[str | None, str | None, str | None] | None:
    rid = int(identity_id or 0)
    if rid <= 0:
        return None

    row = db.execute(
        text(
            """
            SELECT
              COALESCE(NULLIF(TRIM(du.dn), ''), NULLIF(TRIM(du.external_id), ''), NULLIF(TRIM(i.external_id), '')) AS principal_dn,
              COALESCE(
                NULLIF(TRIM(du.username), ''),
                NULLIF(TRIM(du.upn), ''),
                NULLIF(TRIM(i.username), ''),
                NULLIF(TRIM(i.email), '')
              ) AS principal_username,
              COALESCE(
                NULLIF(TRIM(i.display_name), ''),
                NULLIF(TRIM(du.display_name), ''),
                NULLIF(TRIM(i.username), ''),
                NULLIF(TRIM(du.username), ''),
                CAST(i.id AS CHAR)
              ) AS principal_display
            FROM identities i
            LEFT JOIN identity_bindings ib
              ON ib.identity_id = i.id
             AND ib.deleted_at IS NULL
            LEFT JOIN directory_users du
              ON du.id = ib.directory_user_id
            WHERE i.id = :id
            ORDER BY ib.id DESC
            LIMIT 1
            """
        ),
        {"id": rid},
    ).mappings().first()

    if not row:
        return None

    principal_dn = str(row.get("principal_dn") or "").strip() or None
    principal_username = str(row.get("principal_username") or "").strip() or None
    principal_display = str(row.get("principal_display") or "").strip() or None

    if not principal_dn and not principal_username:
        return None

    return principal_dn, principal_username, principal_display


def _resolve_principal_from_requester_identity(
    *,
    db: Session,
    requester_identity_id: int | None,
) -> tuple[str | None, str | None, str | None] | None:
    return _resolve_principal_from_identity_id(
        db=db,
        identity_id=requester_identity_id,
    )


def _resolve_request_principal(
    *,
    db: Session,
    requested_principal_payload: Any,
    requester_identity_id: int | None,
) -> tuple[str | None, str | None, str | None]:
    principal_dn, principal_username, principal_display = _extract_principal_identity(requested_principal_payload)

    if not principal_dn and not principal_username:
        principal_identity_id = _extract_principal_identity_id(requested_principal_payload)
        if principal_identity_id:
            fallback = _resolve_principal_from_identity_id(
                db=db,
                identity_id=principal_identity_id,
            )
            if fallback is not None:
                principal_dn, principal_username, principal_display = fallback

    if not principal_dn and not principal_username:
        fallback = _resolve_principal_from_requester_identity(
            db=db,
            requester_identity_id=requester_identity_id,
        )
        if fallback is not None:
            principal_dn, principal_username, principal_display = fallback

    return principal_dn, principal_username, principal_display


def _insert_item_execution(
    *,
    db: Session,
    access_request_id: int,
    access_request_item_id: int | None,
    status_value: str,
    requested_payload_json: dict[str, Any],
    result_json: dict[str, Any] | None,
    error_message: str | None,
) -> None:
    correlation_id = None
    if isinstance(requested_payload_json, dict):
        correlation_id = str(requested_payload_json.get("correlation_id") or "").strip() or None

    if correlation_id:
        existing = db.execute(
            text(
                """
                SELECT id
                FROM access_request_item_executions
                WHERE access_request_id = :access_request_id
                  AND (
                    (:access_request_item_id IS NULL AND access_request_item_id IS NULL)
                    OR access_request_item_id = :access_request_item_id
                  )
                  AND UPPER(COALESCE(status, '')) = :status
                  AND JSON_UNQUOTE(JSON_EXTRACT(requested_payload_json, '$.correlation_id')) = :correlation_id
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {
                "access_request_id": int(access_request_id),
                "access_request_item_id": int(access_request_item_id) if access_request_item_id else None,
                "status": str(status_value or "DONE").upper(),
                "correlation_id": correlation_id,
            },
        ).mappings().first()
        if existing:
            return

    db.execute(
        text(
            """
            INSERT INTO access_request_item_executions (
              access_request_id,
              access_request_item_id,
              status,
              error_message,
              requested_payload_json,
              result_json,
              started_at,
              finished_at,
              created_at,
              updated_at
            ) VALUES (
              :access_request_id,
              :access_request_item_id,
              :status,
              :error_message,
              :requested_payload_json,
              :result_json,
              NOW(6),
              NOW(6),
              NOW(6),
              NOW(6)
            )
            """
        ),
        {
            "access_request_id": int(access_request_id),
            "access_request_item_id": int(access_request_item_id) if access_request_item_id else None,
            "status": str(status_value or "DONE").upper(),
            "error_message": (str(error_message).strip()[:2000] if error_message else None),
            "requested_payload_json": json.dumps(dict(requested_payload_json or {}), ensure_ascii=False),
            "result_json": (
                json.dumps(dict(result_json or {}), ensure_ascii=False)
                if isinstance(result_json, dict)
                else None
            ),
        },
    )


def _build_access_request_provisioning_plan(
    *,
    db: Session,
    access_request_id: int,
) -> dict[str, Any]:
    req_row = db.execute(
        text(
            """
            SELECT id, requester_identity_id, requested_principal_json
            FROM access_requests
            WHERE id = :id
            LIMIT 1
            """
        ),
        {"id": int(access_request_id)},
    ).mappings().first()

    if not req_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found")

    principal_dn, principal_username, principal_display = _resolve_request_principal(
        db=db,
        requested_principal_payload=req_row.get("requested_principal_json"),
        requester_identity_id=req_row.get("requester_identity_id"),
    )

    rows = db.execute(
        text(
            """
            SELECT id, target_type, target_id, permission
            FROM access_request_items
            WHERE access_request_id = :id
            ORDER BY id ASC
            """
        ),
        {"id": int(access_request_id)},
    ).mappings().all()

    items: list[dict[str, Any]] = []
    errors: list[str] = []

    for row in rows:
        item_id = int(row.get("id") or 0)
        target_type = str(row.get("target_type") or "").strip().lower()
        target_id = int(row.get("target_id") or 0)
        permission = str(row.get("permission") or "").strip().lower()
        normalized_permission = normalize_requested_permission(permission)
        access_level_code = normalized_permission or str(permission or "").strip().upper() or "READ"

        item_plan: dict[str, Any] = {
            "id": item_id,
            "target_type": target_type,
            "target_id": target_id,
            "permission": permission,
            "access_level_code": access_level_code,
            "resolution_status": None,
            "storage_root_access_profile_id": None,
            "access_profile_id": None,
            "access_profile_code": None,
            "group_ref": None,
            "group_name": None,
            "effective_group_ou_dn": None,
            "profile_status": None,
            "group_external_id": None,
            "identity_source_id": None,
            "error": None,
            "error_detail": None,
        }

        resolution = _resolve_implicit_governed_group(
            db=db,
            storage_root_id=int(target_id),
            requested_permission=permission,
            target_type=target_type,
        )
        item_plan["resolution_status"] = str(resolution.get("status") or "")

        if resolution.get("error"):
            detail = dict(resolution.get("error") or {})
            detail["item_id"] = int(item_id or 0) or None
            item_plan["error"] = str(detail.get("message") or "approval blocked")
            item_plan["error_detail"] = detail
            errors.append(_resolution_detail_to_message(item_id=item_id, detail=detail))
            items.append(item_plan)
            continue

        group_ref = str(resolution.get("group_ref") or "").strip()
        if not group_ref:
            detail = {
                "item_id": int(item_id),
                "code": "GOVERNED_GROUP_NAME_MISSING",
                "message": "Resolved governed group has no AD group reference.",
                "hint": "Check naming policy configuration for this storage root.",
                "storage_root_id": int(target_id),
                "requested_permission": access_level_code,
                "candidates_count": 0,
            }
            item_plan["error"] = str(detail.get("message") or "Group reference is missing")
            item_plan["error_detail"] = detail
            errors.append(_resolution_detail_to_message(item_id=item_id, detail=detail))
            items.append(item_plan)
            continue

        item_plan.update(
            {
                "storage_root_access_profile_id": None,
                "access_profile_id": None,
                "access_profile_code": None,
                "group_ref": group_ref,
                "group_name": str(resolution.get("group_name") or "").strip() or None,
                "effective_group_ou_dn": None,
                "profile_status": None,
                "group_external_id": None,
                "identity_source_id": int(resolution.get("identity_source_id") or 0) or None,
            }
        )
        items.append(item_plan)

    return {
        "access_request_id": int(access_request_id),
        "requester_identity_id": int(req_row.get("requester_identity_id") or 0) or None,
        "principal": {
            "dn": principal_dn,
            "username": principal_username,
            "display": principal_display,
        },
        "items": items,
        "errors": errors,
        "can_approve": len(errors) == 0,
    }


def _summarize_visibility_sources_for_request(
    *,
    db: Session,
    access_request_id: int,
) -> dict[str, Any]:
    rows = db.execute(
        text(
            """
            SELECT result_json
            FROM access_request_item_executions
            WHERE access_request_id = :id
              AND UPPER(COALESCE(status, '')) = 'DONE'
            ORDER BY id DESC
            """
        ),
        {"id": int(access_request_id)},
    ).mappings().all()

    visibility_sources: set[str] = set()
    active_snapshot_ids: set[int] = set()
    for row in rows:
        payload = row.get("result_json")
        obj: dict[str, Any] = {}
        if isinstance(payload, dict):
            obj = payload
        elif isinstance(payload, str):
            try:
                parsed = json.loads(payload)
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                obj = parsed

        source = str(obj.get("members_visibility_source") or "").strip()
        if source:
            visibility_sources.add(source)
        snapshot_id = int(obj.get("active_snapshot_id") or 0)
        if snapshot_id > 0:
            active_snapshot_ids.add(snapshot_id)

    return {
        "visibility_sources": sorted(visibility_sources),
        "active_snapshot_ids": sorted(active_snapshot_ids),
    }


def _extract_request_payload(
    *,
    db: Session,
    access_request_id: int,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None, str | None, str | None]:
    req_row = db.execute(
        text(
            """
            SELECT id, requester_identity_id, requested_principal_json
            FROM access_requests
            WHERE id = :id
            LIMIT 1
            """
        ),
        {"id": int(access_request_id)},
    ).mappings().first()
    if not req_row:
        return None, [], None, None, None

    principal_dn, principal_username, principal_display = _resolve_request_principal(
        db=db,
        requested_principal_payload=req_row.get("requested_principal_json"),
        requester_identity_id=req_row.get("requester_identity_id"),
    )
    items = db.execute(
        text(
            """
            SELECT id, target_type, target_id, permission
            FROM access_request_items
            WHERE access_request_id = :id
            ORDER BY id ASC
            """
        ),
        {"id": int(access_request_id)},
    ).mappings().all()
    return dict(req_row), [dict(x) for x in items], principal_dn, principal_username, principal_display


def _remove_ad_groups_for_request(
    *,
    db: Session,
    access_request_id: int,
    request: Request,
) -> tuple[bool, str | None]:
    req_row, items, principal_dn, principal_username, principal_display = _extract_request_payload(
        db=db,
        access_request_id=int(access_request_id),
    )
    if not req_row:
        return False, "Access request not found"
    if not principal_dn and not principal_username:
        return False, "requested_principal_json missing dn/username"
    if not items:
        return False, "No access-request items found"

    failures: list[str] = []
    for item in items:
        item_id = int(item.get("id") or 0)
        target_type = str(item.get("target_type") or "").strip().lower()
        target_id = int(item.get("target_id") or 0)
        permission = str(item.get("permission") or "").strip().lower()

        if target_type != "storage_root" or target_id <= 0:
            _insert_item_execution(
                db=db,
                access_request_id=int(access_request_id),
                access_request_item_id=item_id,
                status_value="FAILED",
                requested_payload_json={
                    "target_type": target_type,
                    "target_id": target_id,
                    "permission": permission,
                    "operation": "revoke",
                },
                result_json=None,
                error_message="Unsupported target_type for AD membership revoke",
            )
            failures.append(f"item#{item_id}: unsupported target")
            continue

        access_level_code = _normalize_access_level_from_permission(permission)
        resolution = _resolve_implicit_governed_group(
            db=db,
            storage_root_id=int(target_id),
            requested_permission=permission,
            target_type=target_type,
        )

        if resolution.get("error"):
            detail = dict(resolution.get("error") or {})
            detail["item_id"] = int(item_id or 0) or None
            _insert_item_execution(
                db=db,
                access_request_id=int(access_request_id),
                access_request_item_id=item_id,
                status_value="FAILED",
                requested_payload_json={
                    "storage_root_id": int(target_id),
                    "access_level_code": str(detail.get("requested_permission") or access_level_code),
                    "permission": permission,
                    "operation": "revoke",
                    "resolution_error": detail,
                },
                result_json=None,
                error_message=str(detail.get("message") or "Unable to resolve governed group for this permission"),
            )
            failures.append(_resolution_detail_to_message(item_id=item_id, detail=detail))
            continue

        group_ref = str(resolution.get("group_ref") or "").strip()
        source_id = int(resolution.get("identity_source_id") or 0) or None
        if not group_ref:
            _insert_item_execution(
                db=db,
                access_request_id=int(access_request_id),
                access_request_item_id=item_id,
                status_value="FAILED",
                requested_payload_json={
                    "storage_root_id": int(target_id),
                    "access_level_code": access_level_code,
                    "group_ref": group_ref or None,
                    "identity_source_id": source_id,
                    "operation": "revoke",
                },
                result_json=None,
                error_message="Missing AD group reference",
            )
            failures.append(f"item#{item_id}: missing group_ref")
            continue

        try:
            membership_payload: dict[str, Any] = {
                "group_ref": group_ref,
                "principal_dn": principal_dn,
                "principal_username": principal_username,
            }
            if source_id:
                membership_payload["identity_source_id"] = int(source_id)
            result = asyncio.run(
                gov_post(
                    request=request,
                    path="/ad-groups/members/remove",
                    payload=membership_payload,
                )
            )
            _insert_item_execution(
                db=db,
                access_request_id=int(access_request_id),
                access_request_item_id=item_id,
                status_value="DONE",
                requested_payload_json={
                    "storage_root_id": int(target_id),
                    "access_level_code": access_level_code,
                    "group_ref": group_ref,
                    "principal_dn": principal_dn,
                    "principal_username": principal_username,
                    "operation": "revoke",
                },
                result_json=result,
                error_message=None,
            )
        except Exception as exc:
            _insert_item_execution(
                db=db,
                access_request_id=int(access_request_id),
                access_request_item_id=item_id,
                status_value="FAILED",
                requested_payload_json={
                    "storage_root_id": int(target_id),
                    "access_level_code": access_level_code,
                    "group_ref": group_ref,
                    "principal_dn": principal_dn,
                    "principal_username": principal_username,
                    "operation": "revoke",
                },
                result_json=None,
                error_message=str(exc),
            )
            failures.append(f"item#{item_id}: {str(exc)[:250]}")

    if failures:
        return False, "; ".join(failures)
    return True, principal_display


def _create_revoke_access_request(
    *,
    db: Session,
    source_request_id: int,
    requester_identity_id: int | None,
) -> int:
    source_row = db.execute(
        text(
            """
            SELECT requested_principal_json, decision_comment
            FROM access_requests
            WHERE id = :id
            LIMIT 1
            """
        ),
        {"id": int(source_request_id)},
    ).mappings().first()
    if not source_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found")

    source_items = db.execute(
        text(
            """
            SELECT target_type, target_id, permission, expires_at
            FROM access_request_items
            WHERE access_request_id = :id
            ORDER BY id ASC
            """
        ),
        {"id": int(source_request_id)},
    ).mappings().all()
    if not source_items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Source request has no items")

    code = f"REVOKE-{int(datetime.utcnow().timestamp())}"
    db.execute(
        text(
            """
            INSERT INTO access_requests (
              code,
              requester_identity_id,
              status,
              decision_comment,
              requested_principal_json,
              created_at,
              updated_at
            ) VALUES (
              :code,
              :requester_identity_id,
              'pending',
              :decision_comment,
              :requested_principal_json,
              NOW(6),
              NOW(6)
            )
            """
        ),
        {
            "code": code,
            "requester_identity_id": requester_identity_id,
            "decision_comment": f"Auto revoke requested from REQ-{int(source_request_id)}",
            "requested_principal_json": source_row.get("requested_principal_json"),
        },
    )
    new_req = db.execute(
        text(
            """
            SELECT id
            FROM access_requests
            WHERE code = :code
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {"code": code},
    ).mappings().first()
    if not new_req:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create revoke request")

    new_req_id = int(new_req["id"])
    for item in source_items:
        db.execute(
            text(
                """
                INSERT INTO access_request_items (
                  access_request_id,
                  target_type,
                  target_id,
                  permission,
                  expires_at,
                  created_at,
                  updated_at
                ) VALUES (
                  :access_request_id,
                  :target_type,
                  :target_id,
                  :permission,
                  :expires_at,
                  NOW(6),
                  NOW(6)
                )
                """
            ),
            {
                "access_request_id": new_req_id,
                "target_type": str(item.get("target_type") or "storage_root"),
                "target_id": int(item.get("target_id") or 0),
                "permission": str(item.get("permission") or "read"),
                "expires_at": item.get("expires_at"),
            },
        )
    return new_req_id


# ============================================================
# INTERNAL ORCHESTRATION HELPERS (governance)
# ============================================================


@internal_router.get(
    "/{access_request_id}/provisioning-plan",
    dependencies=[require_internal({"jobs:read"})],
)
def get_access_request_provisioning_plan_internal(
    access_request_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    require_access_request_review(db, actor_from_request(request), int(access_request_id))
    return _build_access_request_provisioning_plan(
        db=db,
        access_request_id=int(access_request_id),
    )


@internal_router.post(
    "/item-executions",
    dependencies=[require_internal({"jobs:write"})],
)
def create_access_request_item_execution_internal(
    payload: InternalItemExecutionPayload,
    db: Session = Depends(get_db),
):
    _insert_item_execution(
        db=db,
        access_request_id=int(payload.access_request_id),
        access_request_item_id=(
            int(payload.access_request_item_id)
            if payload.access_request_item_id is not None
            else None
        ),
        status_value=str(payload.status or "").strip().upper() or "DONE",
        requested_payload_json=dict(payload.requested_payload_json or {}),
        result_json=dict(payload.result_json) if isinstance(payload.result_json, dict) else None,
        error_message=str(payload.error_message).strip() if payload.error_message else None,
    )
    db.commit()
    return {"ok": True}

# ============================================================
# READ MODELS (VIEWS ONLY)
# ============================================================

@router.get("")
def list_access_requests(
    request: Request,
    status: str | None = None,
    my_action: int | None = None,
    overdue: int | None = None,
    high_impact: int | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    """
    List access requests (V1++).

    Backed by SQL view:
      - v_access_requests
    """
    repo = AccessRequestsViewsRepo(db)
    rows = repo.list(
        status=status,
        my_action=bool(my_action),
        overdue_only=bool(overdue),
        high_impact=bool(high_impact),
        q=q,
    )
    actor = actor_from_request(request)
    rows = filter_access_request_rows(db, actor, rows)
    return ui_list(
        rows,
        meta={
            "status": status,
            "my_action": bool(my_action),
            "overdue": bool(overdue),
            "high_impact": bool(high_impact),
            "q": q,
            "count": int(len(rows)),
        },
    )


@router.get("/counts-by-status")
def access_requests_counts_by_status(
    request: Request,
    my_action: int | None = None,
    overdue: int | None = None,
    high_impact: int | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    repo = AccessRequestsViewsRepo(db)
    rows = repo.list(
        status=None,
        my_action=bool(my_action),
        overdue_only=bool(overdue),
        high_impact=bool(high_impact),
        q=q,
    )
    rows = filter_access_request_rows(db, actor_from_request(request), rows)
    payload: dict[str, int] = {
        "pending": 0,
        "approved": 0,
        "enforced": 0,
        "revoked": 0,
        "rejected": 0,
    }
    for row in rows:
        status_key = str(row.get("status") or "").strip().lower()
        if status_key in payload:
            payload[status_key] += 1
    return ui_data(payload)


@router.get("/{access_request_id}")
def get_access_request_details(
    access_request_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    V1 details + timeline.

    Backed by SQL views:
      - v_access_requests
      - v_access_request_timeline
    """
    repo = AccessRequestsViewsRepo(db)
    row = repo.get_details(access_request_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access request not found",
        )

    require_access_request_access(db, actor_from_request(request), int(access_request_id))
    return ui_data(row, meta={"access_request_id": int(access_request_id)})

# ============================================================
# WRITE MODEL — CREATE
# ============================================================

@router.post("", status_code=status.HTTP_201_CREATED)
def create_access_request(
    payload: AccessRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Create an access request.

    WRITE MODEL ONLY.
    UI refreshes via:
      - GET /access-requests
      - GET /access-requests/{id}/overview
    """
    data = payload.model_dump()
    items = data.pop("items", [])
    permissions = data.pop("permissions", None) or []
    storage_root_id = data.pop("storage_root_id", None)
    expires_at = data.pop("expires_at", None)
    justification = data.pop("justification", None)
    requested_principal = data.pop("requested_principal", None)

    if not data.get("requester_identity_id"):
        identity_header = request.headers.get("x-identity-id")
        if identity_header:
            try:
                data["requester_identity_id"] = int(identity_header)
            except ValueError:
                pass
    actor = actor_from_request(request)
    if not is_platform_administrator(actor) and actor.identity_id is not None:
        data["requester_identity_id"] = int(actor.identity_id)

    if not items and storage_root_id and permissions:
        items = [
            {
                "target_type": "storage_root",
                "target_id": int(storage_root_id),
                "permission": str(permission).lower(),
                "expires_at": expires_at,
            }
            for permission in permissions
            if str(permission).strip()
        ]

    if not items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one access-request item is required",
        )

    if not data.get("code"):
        data["code"] = f"REQ-{int(datetime.utcnow().timestamp())}"

    if justification and not data.get("decision_comment"):
        data["decision_comment"] = str(justification)

    if requested_principal is not None:
        data["requested_principal_json"] = requested_principal
    principal_payload = data.get("requested_principal_json")

    requester_identity_id = int(data.get("requester_identity_id") or 0) or None
    for item in items:
        target_type = str(item.get("target_type") or "").strip().lower()
        target_id = int(item.get("target_id") or 0)
        requested_permission = str(item.get("permission") or "").strip()

        if target_type != "storage_root" or target_id <= 0:
            continue
        guardrail = _evaluate_access_request_guardrails(
            db=db,
            storage_root_id=int(target_id),
            requested_permission=requested_permission,
            requested_principal_payload=principal_payload,
            requester_identity_id=requester_identity_id,
        )
        if not bool(guardrail.get("can_request")):
            event_name = (
                "ACCESS_REQUEST_CREATE_BLOCKED_DUPLICATE"
                if guardrail.get("code") == "ACCESS_REQUEST_ALREADY_EXISTS"
                else "ACCESS_REQUEST_CREATE_BLOCKED_ALREADY_GRANTED"
                if guardrail.get("code") == "ACCESS_ALREADY_GRANTED"
                else "ACCESS_REQUEST_CREATE_BLOCKED"
            )
            log_event(
                logger,
                30,
                event_name,
                storage_root_id=int(target_id),
                user_id=requester_identity_id,
                requested_access_level=normalize_requested_permission(requested_permission),
                current_access_level=guardrail.get("current_access_level"),
                source=guardrail.get("source"),
                outcome="blocked",
                error_code=guardrail.get("code"),
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=dict(guardrail),
            )

    repo = AccessRequestsRepo(db)
    obj = repo.create_with_items(
        request_data={**data, "status": "pending"},
        items=items,
    )

    actor_id, actor_display = _actor_from_headers(request)
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="access_request.created",
        outcome="success",
        target_type="access_request",
        target_id=int(obj.id),
        target_display=str(obj.code or obj.id),
        context_json={
            "items_count": len(items),
            "permissions": permissions,
            "storage_root_id": storage_root_id,
        },
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    log_event(
        logger,
        20,
        "ACCESS_REQUEST_CREATED",
        storage_root_id=storage_root_id,
        user_id=requester_identity_id,
        requested_access_level=",".join(str(item.get("permission") or "").upper() for item in items),
        outcome="success",
    )

    return ui_action(action_id=int(obj.id), message="access_request.created")


@router.post("/check-existing-access")
def check_existing_access(
    payload: ExistingAccessCheckPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    requester_identity_id = int(payload.requester_identity_id or 0) or None
    if requester_identity_id is None:
        identity_header = request.headers.get("x-identity-id")
        if identity_header:
            try:
                requester_identity_id = int(identity_header)
            except ValueError:
                requester_identity_id = None

    requested_permission = str(payload.access_level or payload.permission or "").strip()
    log_event(
        logger,
        20,
        "ACCESS_REQUEST_PRECHECK_STARTED",
        storage_root_id=int(payload.storage_root_id),
        user_id=requester_identity_id,
        requested_access_level=normalize_requested_permission(requested_permission),
        outcome="started",
    )
    result = _evaluate_access_request_guardrails(
        db=db,
        storage_root_id=int(payload.storage_root_id),
        requested_permission=requested_permission,
        requested_principal_payload=payload.requested_principal,
        requester_identity_id=requester_identity_id,
    )
    log_event(
        logger,
        20,
        "ACCESS_REQUEST_PRECHECK_RESULT",
        storage_root_id=int(payload.storage_root_id),
        user_id=requester_identity_id,
        requested_access_level=normalize_requested_permission(requested_permission),
        current_access_level=result.get("current_access_level"),
        source=result.get("source"),
        outcome="allowed" if result.get("can_request") else "blocked",
        error_code=None if result.get("can_request") else result.get("code"),
    )
    return ui_data(result)


# ============================================================
# WRITE MODEL — BULK DECISION (approve/reject/revoke)
# ============================================================


@router.post("/bulk")
def bulk_decision(
    payload: BulkDecisionPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    repo = AccessRequestsRepo(db)
    requested_ids = [int(x) for x in list(payload.ids)]
    decision = str(payload.decision).lower().strip()
    actor = actor_from_request(request)
    actor_id, actor_display = _actor_from_headers(request)
    failed_ids: list[int] = []
    failed_reasons: dict[int, str] = {}
    failed_details: dict[int, dict[str, Any]] = {}
    executions_started = 0

    for req_id in requested_ids:
        require_access_request_review(db, actor, int(req_id))

    if decision == "approve":
        # Governance is now the only business orchestrator for approve/provision.
        # DAL only persists final decision state.
        updated_count = repo.bulk_decision(
            ids=requested_ids,
            decision=decision,
            decision_comment=payload.decision_comment,
        )
        updated_ids = requested_ids
        executions_started = int(updated_count)
    elif decision == "revoke":
        updated_ids = []
        for req_id in requested_ids:
            try:
                ok, detail = _remove_ad_groups_for_request(db=db, access_request_id=int(req_id), request=request)
                if not ok:
                    failed_ids.append(int(req_id))
                    failed_reasons[int(req_id)] = str(detail or "AD group membership revoke failed")
                    failed_details[int(req_id)] = {
                        "item_id": None,
                        "code": "AD_GROUP_MEMBERSHIP_REVOKE_FAILED",
                        "message": str(detail or "AD group membership revoke failed"),
                        "hint": "Verify AD group membership and storage-root binding configuration.",
                        "storage_root_id": None,
                        "requested_permission": None,
                        "candidates_count": 0,
                    }
                    db.execute(
                        text(
                            """
                            UPDATE access_requests
                            SET status = 'approved',
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :id
                            """
                        ),
                        {"id": int(req_id)},
                    )
                    db.commit()
                    continue

                requester_identity_id = actor_id
                if requester_identity_id is None:
                    req_owner = db.execute(
                        text("SELECT requester_identity_id FROM access_requests WHERE id = :id LIMIT 1"),
                        {"id": int(req_id)},
                    ).mappings().first()
                    requester_identity_id = int((req_owner or {}).get("requester_identity_id") or 0) or None

                new_req_id = _create_revoke_access_request(
                    db=db,
                    source_request_id=int(req_id),
                    requester_identity_id=requester_identity_id,
                )

                db.execute(
                    text(
                        """
                        UPDATE access_requests
                        SET status = 'revoked',
                            revoked_at = COALESCE(revoked_at, :now),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {"id": int(req_id), "now": datetime.utcnow()},
                )
                db.commit()
                executions_started += 1
                updated_ids.append(int(req_id))
            except Exception as exc:
                db.rollback()
                failed_ids.append(int(req_id))
                failed_reasons[int(req_id)] = str(exc)
                failed_details[int(req_id)] = {
                    "item_id": None,
                    "code": "REVOKE_RUNTIME_ERROR",
                    "message": str(exc),
                    "hint": "Check DAL/Governance logs for revoke execution details.",
                    "storage_root_id": None,
                    "requested_permission": None,
                    "candidates_count": 0,
                }
        updated_count = len(updated_ids)
    else:
        updated_count = repo.bulk_decision(
            ids=requested_ids,
            decision=decision,
            decision_comment=payload.decision_comment,
        )
        updated_ids = requested_ids

    if updated_ids:
        for req_id in updated_ids:
            visibility_summary = _summarize_visibility_sources_for_request(
                db=db,
                access_request_id=int(req_id),
            )
            log_activity(
                db,
                actor_type="user" if actor_id is not None else "system",
                actor_id=actor_id,
                actor_display=actor_display,
                action=f"access_request.{decision}",
                outcome="success",
                target_type="access_request",
                target_id=int(req_id),
                target_display=f"REQ-{req_id}",
                context_json={
                    "decision": decision,
                    "executions_started": int(executions_started),
                    "members_visibility_sources": visibility_summary.get("visibility_sources", []),
                    "active_snapshot_ids": visibility_summary.get("active_snapshot_ids", []),
                },
                correlation_id=(request.headers.get("x-request-id") or None),
            )

    if failed_ids:
        for req_id in failed_ids:
            log_activity(
                db,
                actor_type="user" if actor_id is not None else "system",
                actor_id=actor_id,
                actor_display=actor_display,
                action=f"access_request.{decision}",
                outcome="failure",
                target_type="access_request",
                target_id=int(req_id),
                target_display=f"REQ-{req_id}",
                context_json={
                    "decision": decision,
                    "error": failed_reasons.get(int(req_id)),
                    "error_detail": failed_details.get(int(req_id)),
                },
                correlation_id=(request.headers.get("x-request-id") or None),
            )

    payload = {
        "ok": len(failed_ids) == 0,
        "decision": decision,
        "requested_ids": requested_ids,
        "updated_ids": updated_ids,
        "failed_ids": failed_ids,
        "failed_reasons": failed_reasons,
        "failed_details": failed_details,
        "updated_count": int(updated_count),
        "executions_started": int(executions_started),
    }
    return ui_data(payload, meta={"count": int(len(updated_ids))})

# ============================================================
# WRITE MODEL — UPDATE
# ============================================================
