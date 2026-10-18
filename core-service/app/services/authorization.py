from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ActorContext:
    identity_id: int | None
    roles: frozenset[str]
    display_name: str | None = None


def _to_int(value: Any) -> int | None:
    raw = str(value or "").strip()
    if not raw.isdigit():
        return None
    parsed = int(raw)
    return parsed if parsed > 0 else None


def actor_from_request(request: Request) -> ActorContext:
    raw_roles = str(request.headers.get("x-roles") or "").strip()
    roles = frozenset(part.strip().lower() for part in raw_roles.split(",") if part.strip())
    return ActorContext(
        identity_id=_to_int(request.headers.get("x-identity-id")),
        roles=roles,
        display_name=str(request.headers.get("x-actor-display") or "").strip() or None,
    )


def is_platform_administrator(actor: ActorContext) -> bool:
    return "platform_admin" in actor.roles or "admin" in actor.roles


def can_access_admin(actor: ActorContext) -> bool:
    return is_platform_administrator(actor)


def can_access_observability(actor: ActorContext) -> bool:
    return is_platform_administrator(actor)


def get_guardian_storage_root_ids(db: Session, actor: ActorContext) -> list[int]:
    if actor.identity_id is None:
        return []
    rows = (
        db.execute(
            text(
                """
                SELECT DISTINCT srr.root_id
                FROM storage_root_roles srr
                WHERE srr.identity_id = :identity_id
                  AND LOWER(COALESCE(srr.role, '')) = 'guardian'
                ORDER BY srr.root_id
                """
            ),
            {"identity_id": int(actor.identity_id)},
        )
        .mappings()
        .all()
    )
    out: list[int] = []
    for row in rows:
        root_id = _to_int(row.get("root_id"))
        if root_id is not None:
            out.append(root_id)
    return out


def is_storage_root_guardian(db: Session, actor: ActorContext, storage_root_id: int) -> bool:
    wanted = int(storage_root_id or 0)
    if wanted <= 0:
        return False
    return wanted in set(get_guardian_storage_root_ids(db, actor))


def can_access_storage_root(db: Session, actor: ActorContext, storage_root_id: int) -> bool:
    if is_platform_administrator(actor):
        return True
    return is_storage_root_guardian(db, actor, int(storage_root_id))


def _request_scope_row(db: Session, access_request_id: int) -> dict[str, Any] | None:
    return (
        db.execute(
            text(
                """
                SELECT
                  ar.id AS access_request_id,
                  ar.requester_identity_id,
                  ari.target_type,
                  ari.target_id
                FROM access_requests ar
                LEFT JOIN access_request_items ari
                  ON ari.id = (
                    SELECT x.id
                    FROM access_request_items x
                    WHERE x.access_request_id = ar.id
                    ORDER BY x.id ASC
                    LIMIT 1
                  )
                WHERE ar.id = :access_request_id
                LIMIT 1
                """
            ),
            {"access_request_id": int(access_request_id)},
        )
        .mappings()
        .first()
    )


def can_access_request(db: Session, actor: ActorContext, access_request_id: int) -> bool:
    if is_platform_administrator(actor):
        return True
    if actor.identity_id is None:
        return False

    row = _request_scope_row(db, int(access_request_id))
    if not row:
        return False

    requester_identity_id = _to_int(row.get("requester_identity_id"))
    if requester_identity_id == actor.identity_id:
        return True

    target_type = str(row.get("target_type") or "").strip().lower()
    target_id = _to_int(row.get("target_id"))
    if target_type == "storage_root" and target_id is not None:
        return can_access_storage_root(db, actor, target_id)
    return False


def can_review_request(db: Session, actor: ActorContext, access_request_id: int) -> bool:
    if is_platform_administrator(actor):
        return True
    if actor.identity_id is None:
        return False

    row = _request_scope_row(db, int(access_request_id))
    if not row:
        return False

    target_type = str(row.get("target_type") or "").strip().lower()
    target_id = _to_int(row.get("target_id"))
    if target_type == "storage_root" and target_id is not None:
        return can_access_storage_root(db, actor, target_id)
    return False


def can_access_storage_roots_index(db: Session, actor: ActorContext) -> bool:
    if is_platform_administrator(actor):
        return True
    return len(get_guardian_storage_root_ids(db, actor)) > 0


def filter_storage_root_rows(db: Session, actor: ActorContext, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if is_platform_administrator(actor):
        return rows
    allowed_root_ids = set(get_guardian_storage_root_ids(db, actor))
    if not allowed_root_ids:
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        root_id = _to_int(row.get("storage_root_id") or row.get("id"))
        if root_id is not None and root_id in allowed_root_ids:
            out.append(row)
    return out


def filter_access_request_rows(db: Session, actor: ActorContext, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if is_platform_administrator(actor):
        return rows
    actor_id = actor.identity_id
    if actor_id is None:
        return []

    guardian_root_ids = set(get_guardian_storage_root_ids(db, actor))
    out: list[dict[str, Any]] = []
    for row in rows:
        requester_identity_id = _to_int(
            row.get("requester_identity_id") or row.get("requester_id") or row.get("identity_id")
        )
        storage_root_id = _to_int(row.get("storage_root_id") or row.get("target_id"))
        if requester_identity_id == actor_id:
            out.append(row)
            continue
        if storage_root_id is not None and storage_root_id in guardian_root_ids:
            out.append(row)
    return out


def require_admin(actor: ActorContext, detail: str = "platform_admin role required") -> None:
    if not can_access_admin(actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def require_observability(actor: ActorContext) -> None:
    if not can_access_observability(actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="observability access forbidden")


def require_storage_root_access(db: Session, actor: ActorContext, storage_root_id: int) -> None:
    if not can_access_storage_root(db, actor, int(storage_root_id)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="storage root access forbidden")


def require_storage_roots_index(db: Session, actor: ActorContext) -> None:
    if not can_access_storage_roots_index(db, actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="storage roots access forbidden")


def require_access_request_access(db: Session, actor: ActorContext, access_request_id: int) -> None:
    if not can_access_request(db, actor, int(access_request_id)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="access request access forbidden")


def require_access_request_review(db: Session, actor: ActorContext, access_request_id: int) -> None:
    if not can_review_request(db, actor, int(access_request_id)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="access request review forbidden")
