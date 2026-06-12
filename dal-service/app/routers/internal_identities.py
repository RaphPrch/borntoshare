from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.security.internal_auth import require_internal


router = APIRouter(
    prefix="/internal/identities",
    tags=["internal-identities"],
    dependencies=[require_internal({"jobs:read"})],
)


class ResolveAdIdentityRequest(BaseModel):
    external_id: str | None = Field(default=None)
    username: str | None = Field(default=None)
    email: str | None = Field(default=None)
    identity_source_id: int | None = Field(default=None, gt=0)
    create_if_missing: bool = Field(default=False)


class ResolveAdIdentityResponse(BaseModel):
    found: bool
    reason_code: str | None = None
    identity_id: str | None = None
    is_active: bool | None = None
    username: str | None = None
    display_name: str | None = None
    email: str | None = None
    external_id: str | None = None


class ResolveAdIdentityBatchRequest(BaseModel):
    identity_source_id: int | None = Field(default=None, gt=0)
    create_if_missing: bool = Field(default=False)
    items: list[ResolveAdIdentityRequest] = Field(default_factory=list)


class ResolveAdIdentityBatchResultItem(BaseModel):
    index: int
    found: bool
    reason_code: str | None = None
    identity_id: str | None = None
    is_active: bool | None = None
    username: str | None = None
    display_name: str | None = None
    email: str | None = None
    external_id: str | None = None


class ResolveAdIdentityBatchResponse(BaseModel):
    count: int
    found: int
    not_found: int
    items: list[ResolveAdIdentityBatchResultItem]


class ResolveLoginIdentityRequest(BaseModel):
    login: str | None = Field(default=None)
    username: str | None = Field(default=None)
    upn_hint: str | None = Field(default=None)
    domain_hint: str | None = Field(default=None)


class ResolveLoginIdentityResponse(BaseModel):
    found: bool
    reason_code: str | None = None
    identity_id: str | None = None
    username: str | None = None
    display_name: str | None = None
    email: str | None = None
    auth_source: str | None = None
    source_id: int | None = None
    external_id: str | None = None
    is_active: bool | None = None
    status: str | None = None
    type: str | None = None
    provisioning_source: str | None = None


@router.post(
    "/resolve-ad/batch",
    response_model=ResolveAdIdentityBatchResponse,
    summary="Resolve multiple AD identities from imported snapshots (internal)",
)
def resolve_ad_identity_batch(
    payload: ResolveAdIdentityBatchRequest,
    db: Session = Depends(get_db),
) -> ResolveAdIdentityBatchResponse:
    out: list[ResolveAdIdentityBatchResultItem] = []

    for index, item in enumerate(payload.items or []):
        effective = ResolveAdIdentityRequest(
            external_id=item.external_id,
            username=item.username,
            email=item.email,
            identity_source_id=item.identity_source_id or payload.identity_source_id,
            create_if_missing=bool(item.create_if_missing or payload.create_if_missing),
        )
        resolved = resolve_ad_identity(effective, db=db)
        out.append(
            ResolveAdIdentityBatchResultItem(
                index=index,
                found=bool(resolved.found),
                reason_code=resolved.reason_code,
                identity_id=resolved.identity_id,
                is_active=resolved.is_active,
                username=resolved.username,
                display_name=resolved.display_name,
                email=resolved.email,
                external_id=resolved.external_id,
            )
        )

    found_count = sum(1 for it in out if it.found)
    return ResolveAdIdentityBatchResponse(
        count=len(out),
        found=found_count,
        not_found=len(out) - found_count,
        items=out,
    )


@router.post(
    "/resolve-ad",
    response_model=ResolveAdIdentityResponse,
    summary="Resolve AD identity from imported snapshots (internal)",
)
def resolve_ad_identity(
    payload: ResolveAdIdentityRequest,
    db: Session = Depends(get_db),
) -> ResolveAdIdentityResponse:
    candidates = [
        str(payload.external_id or "").strip(),
        str(payload.username or "").strip(),
        str(payload.email or "").strip(),
    ]
    candidates = [c for c in candidates if c]
    if not candidates:
        return ResolveAdIdentityResponse(found=False, reason_code="NO_CANDIDATE")

    source_id = int(payload.identity_source_id or 0) or None

    def _find_existing_identity(candidate: str) -> dict[str, Any] | None:
        return db.execute(
            text(
                """
                SELECT
                  i.id,
                  i.username,
                  i.display_name,
                  i.email,
                  i.external_id,
                  i.is_active
                FROM identities i
                WHERE i.auth_source = 'ad'
                  AND (:source_id IS NULL OR i.source_id = :source_id)
                  AND (
                    LOWER(TRIM(COALESCE(i.external_id, ''))) = LOWER(:candidate)
                    OR LOWER(TRIM(COALESCE(i.username, ''))) = LOWER(:candidate)
                    OR LOWER(TRIM(COALESCE(i.email, ''))) = LOWER(:candidate)
                  )
                ORDER BY i.id ASC
                LIMIT 1
                """
            ),
            {
                "candidate": candidate,
                "source_id": source_id,
            },
        ).mappings().first()

    # Priority order preserves caller intent: external_id, username, email
    for candidate in candidates:
        row = _find_existing_identity(candidate)
        if row:
            return ResolveAdIdentityResponse(
                found=True,
                reason_code="FOUND_EXISTING",
                identity_id=str(row.get("id")),
                is_active=bool(row.get("is_active")),
                username=row.get("username"),
                display_name=row.get("display_name"),
                email=row.get("email"),
                external_id=row.get("external_id"),
            )

    if bool(payload.create_if_missing) and source_id is not None:
        snapshot_user = db.execute(
            text(
                """
                SELECT
                  dsu.external_id,
                  dsu.username,
                  dsu.display_name,
                  dsu.email,
                  dsu.is_active
                FROM directory_snapshot_users dsu
                JOIN directory_snapshots ds ON ds.id = dsu.snapshot_id
                WHERE dsu.identity_source_id = :source_id
                  AND (
                    LOWER(TRIM(COALESCE(dsu.external_id, ''))) IN :candidates
                    OR LOWER(TRIM(COALESCE(dsu.dn, ''))) IN :candidates
                    OR LOWER(TRIM(COALESCE(dsu.username, ''))) IN :candidates
                    OR LOWER(TRIM(COALESCE(dsu.upn, ''))) IN :candidates
                    OR LOWER(TRIM(COALESCE(dsu.email, ''))) IN :candidates
                  )
                  AND UPPER(COALESCE(ds.status, '')) IN ('ACTIVE', 'SUCCEEDED')
                ORDER BY
                  CASE WHEN UPPER(COALESCE(ds.status, '')) = 'ACTIVE' THEN 0 ELSE 1 END,
                  COALESCE(ds.activated_at, ds.completed_at, ds.finished_at, ds.started_at, ds.created_at) DESC,
                  dsu.id DESC
                LIMIT 1
                """
            ),
            {
                "source_id": source_id,
                "candidates": tuple(c.strip().lower() for c in candidates),
            },
        ).mappings().first()

        if snapshot_user:
            external_id = str(snapshot_user.get("external_id") or "").strip()
            username = str(snapshot_user.get("username") or "").strip() or None
            display_name = str(snapshot_user.get("display_name") or username or external_id).strip() or external_id
            email = str(snapshot_user.get("email") or "").strip() or None
            is_active = bool(snapshot_user.get("is_active")) if snapshot_user.get("is_active") is not None else True

            if external_id:
                db.execute(
                    text(
                        """
                        INSERT INTO identities (
                          source_id,
                          username,
                          type,
                          external_id,
                          display_name,
                          email,
                          auth_source,
                          is_active,
                          snapshot_version,
                          snapshot_source,
                          provisioning_source,
                          status,
                          created_at,
                          updated_at
                        ) VALUES (
                          :source_id,
                          :username,
                          'user',
                          :external_id,
                          :display_name,
                          :email,
                          'ad',
                          :is_active,
                          1,
                          'internal_resolve_ad',
                          'explicit',
                          :status,
                          NOW(),
                          NOW()
                        )
                        """
                    ),
                    {
                        "source_id": source_id,
                        "username": username,
                        "external_id": external_id,
                        "display_name": display_name,
                        "email": email,
                        "is_active": 1 if is_active else 0,
                        "status": "active" if is_active else "inactive",
                    },
                )
                db.commit()

                created_row = _find_existing_identity(external_id)
                if created_row:
                    return ResolveAdIdentityResponse(
                        found=True,
                        reason_code="CREATED_FROM_SNAPSHOT",
                        identity_id=str(created_row.get("id")),
                        is_active=bool(created_row.get("is_active")),
                        username=created_row.get("username"),
                        display_name=created_row.get("display_name"),
                        email=created_row.get("email"),
                        external_id=created_row.get("external_id"),
                    )
    return ResolveAdIdentityResponse(found=False, reason_code="NOT_FOUND")


@router.post(
    "/resolve-login",
    response_model=ResolveLoginIdentityResponse,
    summary="Resolve application identity for login (internal)",
)
def resolve_login_identity(
    payload: ResolveLoginIdentityRequest,
    db: Session = Depends(get_db),
) -> ResolveLoginIdentityResponse:
    username = str(payload.username or "").strip()
    upn_hint = str(payload.upn_hint or "").strip()
    domain_hint = str(payload.domain_hint or "").strip().lower()

    if not username and not upn_hint:
        return ResolveLoginIdentityResponse(found=False, reason_code="NO_CANDIDATE")

    row = db.execute(
        text(
            """
            SELECT
              i.id,
              i.username,
              i.display_name,
              i.email,
              i.auth_source,
              i.source_id,
              i.external_id,
              i.is_active,
              i.status,
              i.type,
              COALESCE(i.provisioning_source, 'explicit') AS provisioning_source
            FROM identities i
            WHERE LOWER(COALESCE(i.type, 'user')) = 'user'
              AND COALESCE(i.provisioning_source, 'explicit') <> 'legacy_auto_snapshot'
              AND (
                (:username <> '' AND LOWER(TRIM(COALESCE(i.username, ''))) = LOWER(:username))
                OR
                (:upn_hint <> '' AND LOWER(TRIM(COALESCE(i.email, ''))) = LOWER(:upn_hint))
              )
            ORDER BY
              CASE
                WHEN :upn_hint <> '' AND LOWER(TRIM(COALESCE(i.email, ''))) = LOWER(:upn_hint) THEN 0
                WHEN :domain_hint <> '' AND LOWER(COALESCE(i.auth_source, '')) = 'ad' THEN 1
                WHEN :domain_hint = '' AND :upn_hint = '' AND LOWER(COALESCE(i.auth_source, '')) = 'local' THEN 2
                WHEN LOWER(COALESCE(i.auth_source, '')) = 'ad' THEN 3
                ELSE 4
              END,
              i.is_active DESC,
              i.id ASC
            LIMIT 1
            """
        ),
        {
            "username": username,
            "upn_hint": upn_hint,
            "domain_hint": domain_hint,
        },
    ).mappings().first()

    if not row:
        return ResolveLoginIdentityResponse(found=False, reason_code="NOT_FOUND")

    return ResolveLoginIdentityResponse(
        found=True,
        reason_code="FOUND",
        identity_id=str(row.get("id")),
        username=row.get("username"),
        display_name=row.get("display_name"),
        email=row.get("email"),
        auth_source=row.get("auth_source"),
        source_id=int(row.get("source_id")) if row.get("source_id") is not None else None,
        external_id=row.get("external_id"),
        is_active=bool(row.get("is_active")) if row.get("is_active") is not None else None,
        status=row.get("status"),
        type=row.get("type"),
        provisioning_source=row.get("provisioning_source"),
    )
