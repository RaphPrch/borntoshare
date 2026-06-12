from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.identity_sources import IdentitySource
from app.routers.internal_auth_local import _hash_b2s_password
from app.routers._helpers import ui_data, ui_list
from app.schemas.identity_search import IdentitySearchRequest
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request


router = APIRouter(prefix="/identity", tags=["identity"])

_APP_ROLE_CODE_MAP = {
    "user": "user",
    "platform_admin": "platform_admin",
    "platform_administrator": "platform_admin",
}


def _actor_from_headers(request: Request) -> tuple[int | None, str | None]:
    actor = actor_from_request(request)
    return actor.identity_id, actor.display_name


def _pick_identity_source(db: Session, source_id: int | None) -> IdentitySource | None:
    if source_id is not None:
        src = db.get(IdentitySource, int(source_id))
        if src and str(getattr(src, "type", "") or "").lower() == "ad" and bool(getattr(src, "is_active", True)):
            return src

    row = db.execute(
        text(
            """
            SELECT id
            FROM identity_sources
            WHERE type = 'ad' AND is_active = 1
            ORDER BY id ASC
            LIMIT 1
            """
        )
    ).mappings().first()
    if not row:
        return None
    return db.get(IdentitySource, int(row["id"]))


def _pick_local_identity_source_id(db: Session, source_id: int | None) -> int | None:
    if source_id is not None:
        row = db.execute(
            text(
                """
                SELECT id
                FROM identity_sources
                WHERE id = :id
                  AND LOWER(COALESCE(type, '')) IN ('local', 'internal')
                  AND is_active = 1
                LIMIT 1
                """
            ),
            {"id": int(source_id)},
        ).mappings().first()
        if row:
            return int(row["id"])

    row = db.execute(
        text(
            """
            SELECT id
            FROM identity_sources
            WHERE LOWER(COALESCE(type, '')) IN ('local', 'internal')
              AND is_active = 1
            ORDER BY id ASC
            LIMIT 1
            """
        )
    ).mappings().first()
    if row:
        return int(row["id"])

    row = db.execute(
        text(
            """
            SELECT source_id AS id
            FROM identities
            WHERE LOWER(COALESCE(auth_source, '')) IN ('local', 'internal')
              AND source_id IS NOT NULL
            ORDER BY id ASC
            LIMIT 1
            """
        )
    ).mappings().first()
    if row:
        return int(row["id"])
    return None


def _moved_to_governance(*, error_code: str, message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "error_code": error_code,
            "message": message,
        },
    )


def _normalize_identity_type(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in {"user", "group"}:
        return raw
    return None


def _normalize_app_role(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    return _APP_ROLE_CODE_MAP.get(raw)


def _clean_text(value: Any) -> str | None:
    text_value = str(value or "").strip()
    return text_value or None


def _is_default_local_admin_row(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    auth_source = str(row.get("auth_source") or "").strip().lower()
    username = str(row.get("username") or "").strip().lower()
    provisioning_source = str(row.get("provisioning_source") or "").strip().lower()
    return auth_source in {"local", "internal"} and provisioning_source == "system" and username == "admin"


def _ensure_role_id(db: Session, role_code: str) -> int:
    row = db.execute(
        text(
            """
            SELECT id
            FROM roles
            WHERE code = :code
            LIMIT 1
            """
        ),
        {"code": role_code},
    ).mappings().first()
    if row:
        return int(row["id"])

    labels = {
        "user": ("User", "Basic access to application features"),
        "platform_admin": ("Platform administrator", "Full administrative access within the application"),
    }
    label, description = labels.get(role_code, (role_code.replace("_", " ").title(), None))
    db.execute(
        text(
            """
            INSERT INTO roles (code, label, description, created_at, updated_at)
            VALUES (:code, :label, :description, NOW(), NOW())
            """
        ),
        {
            "code": role_code,
            "label": label,
            "description": description,
        },
    )
    row = db.execute(
        text(
            """
            SELECT id
            FROM roles
            WHERE code = :code
            LIMIT 1
            """
        ),
        {"code": role_code},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Application role '{role_code}' is unavailable")
    return int(row["id"])


def _set_subject_application_role(
    *,
    db: Session,
    identity_id: int | None,
    directory_group_id: int | None,
    role_code: str,
) -> None:
    role_id = _ensure_role_id(db, role_code)
    db.execute(
        text(
            """
            DELETE ir
            FROM identity_roles ir
            JOIN roles r ON r.id = ir.role_id
            WHERE (
                (:identity_id IS NOT NULL AND ir.identity_id = :identity_id)
                OR
                (:directory_group_id IS NOT NULL AND ir.directory_group_id = :directory_group_id)
            )
              AND r.code IN ('user', 'platform_admin')
            """
        ),
        {
            "identity_id": int(identity_id) if identity_id is not None else None,
            "directory_group_id": int(directory_group_id) if directory_group_id is not None else None,
        },
    )
    db.execute(
        text(
            """
            INSERT INTO identity_roles (
              identity_id,
              directory_group_id,
              role_id,
              source,
              created_at
            ) VALUES (
              :identity_id,
              :directory_group_id,
              :role_id,
              'manual',
              NOW()
            )
            """
        ),
        {
            "identity_id": int(identity_id) if identity_id is not None else None,
            "directory_group_id": int(directory_group_id) if directory_group_id is not None else None,
            "role_id": int(role_id),
        },
    )


@router.get("")
def list_identity_overview(
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    normalized_scope = str(scope or "").strip().lower()
    admin_login_scope = normalized_scope in {"admin_login", "admin", "login"}

    if admin_login_scope:
        user_rows = db.execute(
            text(
                """
                SELECT
                  i.id,
                  i.username,
                  i.display_name,
                  i.email,
                  i.auth_source,
                  i.external_id,
                  i.source_id,
                  i.is_active,
                  i.type,
                  i.snapshot_source,
                  COALESCE(i.provisioning_source, 'explicit') AS provisioning_source,
                  i.status,
                  i.created_at,
                  i.updated_at,
                  i.last_snapshot_at,
                  ids.name AS source_name
                FROM identities i
                LEFT JOIN identity_sources ids ON ids.id = i.source_id
                WHERE LOWER(COALESCE(i.type, 'user')) = 'user'
                  AND LOWER(COALESCE(i.auth_source, '')) = 'local'
                ORDER BY i.id DESC
                LIMIT 500
                """
            )
        ).mappings().all()
        group_rows = []
    else:
        user_rows = db.execute(
            text(
                """
                SELECT
                  i.id,
                  i.username,
                  i.display_name,
                  i.email,
                  i.auth_source,
                  i.external_id,
                  i.source_id,
                  i.is_active,
                  i.type,
                  i.snapshot_source,
                  COALESCE(i.provisioning_source, 'explicit') AS provisioning_source,
                  i.status,
                  i.created_at,
                  i.updated_at,
                  i.last_snapshot_at,
                  ids.name AS source_name
                FROM identities i
                LEFT JOIN identity_sources ids ON ids.id = i.source_id
                WHERE COALESCE(i.provisioning_source, 'explicit') <> 'legacy_auto_snapshot'
                ORDER BY i.id DESC
                LIMIT 500
                """
            )
        ).mappings().all()
        group_rows = db.execute(
            text(
                """
                SELECT
                  dg.id,
                  dg.external_id,
                  dg.dn,
                  dg.identity_source_id,
                  dg.name AS display_name,
                  dg.created_at,
                  dg.updated_at,
                  dg.last_snapshot_at,
                  ids.name AS source_name,
                  (
                    SELECT COUNT(*)
                    FROM directory_group_members dgm
                    WHERE dgm.group_id = dg.id
                      AND dgm.deleted_at IS NULL
                  ) AS members_count
                FROM directory_groups dg
                LEFT JOIN identity_sources ids ON ids.id = dg.identity_source_id
                WHERE dg.deleted_at IS NULL
                  AND EXISTS (
                    SELECT 1
                    FROM identity_roles ir
                    JOIN roles r ON r.id = ir.role_id
                    WHERE ir.directory_group_id = dg.id
                      AND r.code IN ('user', 'platform_admin')
                  )
                ORDER BY dg.id DESC
                LIMIT 500
                """
            )
        ).mappings().all()

    identity_ids = [int(row.get("id")) for row in user_rows if row.get("id") is not None]
    group_ids = [int(row.get("id")) for row in group_rows if row.get("id") is not None]
    user_roles: dict[int, list[str]] = {}
    group_roles: dict[int, list[str]] = {}

    if identity_ids:
        role_rows = db.execute(
            text(
                """
                SELECT identity_id, role_code
                FROM v_identity_effective_roles
                WHERE identity_id IN :ids
                ORDER BY identity_id, role_code
                """
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": identity_ids},
        ).mappings().all()
        for role_row in role_rows:
            user_roles.setdefault(int(role_row["identity_id"]), []).append(str(role_row["role_code"]))

    if group_ids:
        role_rows = db.execute(
            text(
                """
                SELECT ir.directory_group_id, r.code AS role_code
                FROM identity_roles ir
                JOIN roles r ON r.id = ir.role_id
                WHERE ir.directory_group_id IN :ids
                ORDER BY ir.directory_group_id, r.code
                """
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": group_ids},
        ).mappings().all()
        for role_row in role_rows:
            group_roles.setdefault(int(role_row["directory_group_id"]), []).append(str(role_row["role_code"]))

    users = [
        {
            "id": row.get("id"),
            "type": str(row.get("type") or "user").lower(),
            "username": row.get("username"),
            "display_name": row.get("display_name"),
            "email": row.get("email"),
            "auth_source": row.get("auth_source"),
            "external_id": row.get("external_id"),
            "identity_source_id": row.get("source_id"),
            "source_name": row.get("source_name"),
            "snapshot_source": row.get("snapshot_source"),
            "provisioning_source": row.get("provisioning_source"),
            "is_active": bool(row.get("is_active")) if row.get("is_active") is not None else None,
            "is_admin": "platform_admin" in set(user_roles.get(int(row.get("id") or 0), [])),
            "status": row.get("status"),
            "roles": user_roles.get(int(row.get("id") or 0), []),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "last_snapshot_at": row.get("last_snapshot_at"),
        }
        for row in user_rows
    ]

    groups = [
        {
            "id": row.get("id"),
            "type": "group",
            "username": row.get("display_name"),
            "display_name": row.get("display_name"),
            "email": None,
            "auth_source": "ad",
            "external_id": row.get("external_id"),
            "dn": row.get("external_id"),
            "identity_source_id": row.get("identity_source_id"),
            "source_name": row.get("source_name"),
            "members_count": int(row.get("members_count") or 0),
            "roles": group_roles.get(int(row.get("id") or 0), []),
            "is_active": True,
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
        for row in group_rows
    ]

    items = [*users, *groups]
    return ui_data(
        {
            "users": users,
            "groups": groups,
            "items": items,
        },
        meta={
            "users_count": int(len(users)),
            "groups_count": int(len(groups)),
            "count": int(len(items)),
        },
    )


@router.post("")
async def create_identity(
    request: Request,
    payload: dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
):
    identity_type = _normalize_identity_type(payload.get("identity_type"))
    auth_source = str(payload.get("auth_source") or "").strip().lower()
    application_role = _normalize_app_role(payload.get("application_role"))
    principal = payload.get("principal") if isinstance(payload.get("principal"), dict) else {}

    if identity_type not in {"user", "group"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="identity_type must be user or group")
    if auth_source not in {"local", "ad"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="auth_source must be local or ad")
    if not application_role:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="application_role must be one of: user, platform_admin",
        )
    if auth_source == "local" and identity_type != "user":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Local identities support users only")
    if auth_source == "ad" and identity_type == "group" and str(principal.get("type") or "group").strip().lower() not in {"", "group"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="principal.type must be group")

    created = False
    subject_type = identity_type
    row: dict[str, Any] | None = None
    target_id: int | None = None

    if auth_source == "local":
        username = _clean_text(payload.get("username"))
        display_name = _clean_text(payload.get("display_name"))
        email = _clean_text(payload.get("email"))
        password = str(payload.get("temporary_password") or "")

        if not username or not display_name or not password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="username, display_name and temporary_password are required",
            )

        local_source_id = _pick_local_identity_source_id(db, payload.get("identity_source_id"))
        if local_source_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No active local identity source is configured")

        duplicate = db.execute(
            text(
                """
                SELECT id
                FROM identities
                WHERE LOWER(COALESCE(username, '')) = LOWER(:username)
                  AND LOWER(COALESCE(auth_source, '')) IN ('local', 'internal')
                LIMIT 1
                """
            ),
            {"username": username},
        ).mappings().first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A local identity with this username already exists")

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
                  'local',
                  1,
                  1,
                  NULL,
                  'explicit',
                  'active',
                  NOW(),
                  NOW()
                )
                """
            ),
            {
                "source_id": int(local_source_id),
                "username": username,
                "external_id": username,
                "display_name": display_name,
                "email": email,
            },
        )
        row = db.execute(
            text(
                """
                SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type
                FROM identities
                WHERE source_id = :source_id
                  AND external_id = :external_id
                LIMIT 1
                """
            ),
            {"source_id": int(local_source_id), "external_id": username},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Local identity creation failed")

        target_id = int(row["id"])
        db.execute(
            text(
                """
                INSERT INTO local_credentials (
                  identity_id,
                  password_hash,
                  password_version,
                  last_rotated_at,
                  created_at,
                  updated_at,
                  deleted_at
                ) VALUES (
                  :identity_id,
                  :password_hash,
                  'b2s$v=1$bcrypt',
                  NOW(),
                  NOW(),
                  NOW(),
                  NULL
                )
                """
            ),
            {
                "identity_id": target_id,
                "password_hash": _hash_b2s_password(password),
            },
        )
        _set_subject_application_role(
            db=db,
            identity_id=target_id,
            directory_group_id=None,
            role_code=application_role,
        )
        created = True
    elif identity_type == "user":
        identity_source = _pick_identity_source(db, payload.get("identity_source_id"))
        if identity_source is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No active AD identity source is configured")

        external_id = _clean_text(principal.get("external_id")) or _clean_text(principal.get("dn")) or _clean_text(principal.get("username")) or _clean_text(principal.get("upn")) or _clean_text(principal.get("email"))
        username = _clean_text(principal.get("username")) or _clean_text(principal.get("upn")) or _clean_text(principal.get("email"))
        display_name = _clean_text(principal.get("display_name")) or username or external_id
        email = _clean_text(principal.get("email"))
        if not external_id or not display_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="principal external_id/dn and display_name are required")

        existing = db.execute(
            text(
                """
                SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type
                FROM identities
                WHERE source_id = :source_id
                  AND external_id = :external_id
                LIMIT 1
                """
            ),
            {"source_id": int(identity_source.id), "external_id": external_id},
        ).mappings().first()

        if existing:
            target_id = int(existing["id"])
            db.execute(
                text(
                    """
                    UPDATE identities
                    SET username = :username,
                        display_name = :display_name,
                        email = :email,
                        auth_source = 'ad',
                        is_active = 1,
                        snapshot_source = NULL,
                        provisioning_source = 'explicit',
                        status = 'active',
                        updated_at = NOW(6)
                    WHERE id = :id
                    """
                ),
                {
                    "id": target_id,
                    "username": username,
                    "display_name": display_name,
                    "email": email,
                },
            )
            row = db.execute(
                text(
                    """
                    SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type
                    FROM identities
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
                {"id": target_id},
            ).mappings().first()
        else:
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
                      1,
                      1,
                      NULL,
                      'explicit',
                      'active',
                      NOW(),
                      NOW()
                    )
                    """
                ),
                {
                    "source_id": int(identity_source.id),
                    "username": username,
                    "external_id": external_id,
                    "display_name": display_name,
                    "email": email,
                },
            )
            row = db.execute(
                text(
                    """
                    SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type
                    FROM identities
                    WHERE source_id = :source_id
                      AND external_id = :external_id
                    LIMIT 1
                    """
                ),
                {"source_id": int(identity_source.id), "external_id": external_id},
            ).mappings().first()
            created = True
            if row:
                target_id = int(row["id"])

        if target_id is None or not row:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Directory user creation failed")

        _set_subject_application_role(
            db=db,
            identity_id=target_id,
            directory_group_id=None,
            role_code=application_role,
        )
    else:
        identity_source = _pick_identity_source(db, payload.get("identity_source_id"))
        if identity_source is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No active AD identity source is configured")

        external_id = _clean_text(principal.get("external_id")) or _clean_text(principal.get("dn")) or _clean_text(principal.get("username"))
        display_name = _clean_text(principal.get("display_name")) or _clean_text(principal.get("name")) or external_id
        dn = _clean_text(principal.get("dn"))
        if not external_id or not display_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="principal external_id/dn and display_name are required")

        group_row = db.execute(
            text(
                """
                SELECT id, name, external_id, identity_source_id
                FROM directory_groups
                WHERE identity_source_id = :source_id
                  AND external_id = :external_id
                  AND deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"source_id": int(identity_source.id), "external_id": external_id},
        ).mappings().first()

        if group_row:
            target_id = int(group_row["id"])
            db.execute(
                text(
                    """
                    UPDATE directory_groups
                    SET name = :display_name,
                        dn = :dn,
                        snapshot_source = NULL,
                        updated_at = NOW(6)
                    WHERE id = :id
                    """
                ),
                {
                    "id": target_id,
                    "display_name": display_name,
                    "dn": dn,
                },
            )
        else:
            db.execute(
                text(
                    """
                    INSERT INTO directory_groups (
                      identity_source_id,
                      external_id,
                      dn,
                      name,
                      snapshot_version,
                      snapshot_source,
                      snapshot_hash,
                      last_snapshot_at,
                      captured_at,
                      created_at,
                      updated_at,
                      deleted_at
                    ) VALUES (
                      :source_id,
                      :external_id,
                      :dn,
                      :display_name,
                      1,
                      NULL,
                      NULL,
                      NULL,
                      NOW(),
                      NOW(),
                      NOW(),
                      NULL
                    )
                    """
                ),
                {
                    "source_id": int(identity_source.id),
                    "external_id": external_id,
                    "dn": dn,
                    "display_name": display_name,
                },
            )
            created = True
            group_row = db.execute(
                text(
                    """
                    SELECT id, name, external_id, identity_source_id
                    FROM directory_groups
                    WHERE identity_source_id = :source_id
                      AND external_id = :external_id
                      AND deleted_at IS NULL
                    LIMIT 1
                    """
                ),
                {"source_id": int(identity_source.id), "external_id": external_id},
            ).mappings().first()
            if group_row:
                target_id = int(group_row["id"])

        if target_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Directory group creation failed")

        _set_subject_application_role(
            db=db,
            identity_id=None,
            directory_group_id=target_id,
            role_code=application_role,
        )
        row = db.execute(
            text(
                """
                SELECT
                  dg.id,
                  'group' AS type,
                  dg.name AS username,
                  dg.name AS display_name,
                  NULL AS email,
                  'ad' AS auth_source,
                  dg.external_id,
                  dg.identity_source_id AS source_id,
                  NULL AS is_active
                FROM directory_groups dg
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": target_id},
        ).mappings().first()

    if not row or target_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Identity creation failed")

    db.commit()

    actor_id, actor_display = _actor_from_headers(request)
    target_display = str(row.get("display_name") or row.get("username") or target_id)
    correlation_id = request.headers.get("x-request-id") or None
    target_type = "identity_group" if subject_type == "group" else "identity"

    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="identity.account_created" if subject_type == "user" else "identity.group_access_granted",
        outcome="success",
        target_type=target_type,
        target_id=target_id,
        target_display=target_display,
        context_json={
            "auth_source": auth_source,
            "application_role": application_role,
            "created": created,
        },
        correlation_id=correlation_id,
    )

    return ui_data(
        {
            "id": row.get("id"),
            "type": str(row.get("type") or subject_type).lower(),
            "username": row.get("username"),
            "display_name": row.get("display_name"),
            "email": row.get("email"),
            "auth_source": row.get("auth_source"),
            "external_id": row.get("external_id"),
            "identity_source_id": row.get("source_id"),
            "is_active": bool(row.get("is_active")) if row.get("is_active") is not None else None,
            "application_role": application_role,
        },
        meta={"identity_id": target_id, "identity_type": subject_type, "created": created},
    )


@router.get("/groups/{group_id}/members")
def list_identity_group_members(
    group_id: int,
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            """
            SELECT
              du.id,
              du.username,
              du.display_name,
              du.email,
              du.status,
              du.is_active
            FROM directory_group_members dgm
            JOIN directory_users du ON du.id = dgm.directory_user_id
            WHERE dgm.group_id = :group_id
              AND dgm.deleted_at IS NULL
            ORDER BY COALESCE(NULLIF(TRIM(du.display_name), ''), du.username, du.email, CAST(du.id AS CHAR))
            LIMIT 500
            """
        ),
        {"group_id": int(group_id)},
    ).mappings().all()
    return ui_list(
        [
            {
                "id": row.get("id"),
                "username": row.get("username"),
                "display_name": row.get("display_name"),
                "email": row.get("email"),
                "status": row.get("status"),
                "is_active": bool(row.get("is_active")) if row.get("is_active") is not None else None,
            }
            for row in rows
        ],
        meta={"group_id": int(group_id), "count": len(rows)},
    )


@router.delete("/{identity_id}")
async def delete_identity(
    identity_id: int,
    request: Request,
    identity_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    normalized_type = _normalize_identity_type(identity_type) if identity_type is not None else None
    actor_id, actor_display = _actor_from_headers(request)
    correlation_id = request.headers.get("x-request-id") or None

    if normalized_type == "group":
        group_row = db.execute(
            text(
                """
                SELECT
                  dg.id,
                  dg.name AS display_name,
                  dg.external_id,
                  dg.identity_source_id AS source_id,
                  'ad' AS auth_source,
                  'group' AS type
                FROM directory_groups dg
                WHERE dg.id = :id
                  AND dg.deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"id": int(identity_id)},
        ).mappings().first()
        if not group_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity not found")

        db.execute(
            text(
                """
                DELETE FROM identity_roles
                WHERE directory_group_id = :id
                """
            ),
            {"id": int(identity_id)},
        )
        db.commit()

        log_activity(
            db,
            actor_type="user" if actor_id is not None else "system",
            actor_id=actor_id,
            actor_display=actor_display,
            action="identity.group_access_revoked",
            outcome="success",
            target_type="identity_group",
            target_id=int(identity_id),
            target_display=str(group_row.get("display_name") or group_row.get("external_id") or identity_id),
            context_json={"identity_type": "group", "deleted": True},
            correlation_id=correlation_id,
        )

        return ui_data(
            {"id": int(identity_id), "type": "group", "deleted": True},
            meta={"identity_id": int(identity_id), "identity_type": "group", "deleted": True},
        )

    user_row = db.execute(
        text(
            """
            SELECT
              i.id,
              i.username,
              i.display_name,
              i.auth_source,
              i.provisioning_source,
              i.type
            FROM identities i
            WHERE i.id = :id
            LIMIT 1
            """
        ),
        {"id": int(identity_id)},
    ).mappings().first()

    if not user_row and normalized_type is None:
        group_row = db.execute(
            text(
                """
                SELECT
                  dg.id,
                  dg.name AS display_name,
                  dg.external_id,
                  dg.identity_source_id AS source_id,
                  'ad' AS auth_source,
                  'group' AS type
                FROM directory_groups dg
                WHERE dg.id = :id
                  AND dg.deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"id": int(identity_id)},
        ).mappings().first()
        if group_row:
            db.execute(
                text(
                    """
                    DELETE FROM identity_roles
                    WHERE directory_group_id = :id
                    """
                ),
                {"id": int(identity_id)},
            )
            db.commit()
            log_activity(
                db,
                actor_type="user" if actor_id is not None else "system",
                actor_id=actor_id,
                actor_display=actor_display,
                action="identity.group_access_revoked",
                outcome="success",
                target_type="identity_group",
                target_id=int(identity_id),
                target_display=str(group_row.get("display_name") or group_row.get("external_id") or identity_id),
                context_json={"identity_type": "group", "deleted": True},
                correlation_id=correlation_id,
            )
            return ui_data(
                {"id": int(identity_id), "type": "group", "deleted": True},
                meta={"identity_id": int(identity_id), "identity_type": "group", "deleted": True},
            )

    if not user_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity not found")

    if _is_default_local_admin_row(user_row):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Default local admin cannot be deleted",
        )

    db.execute(
        text(
            """
            DELETE FROM identity_bindings
            WHERE identity_id = :id
            """
        ),
        {"id": int(identity_id)},
    )
    db.execute(
        text(
            """
            DELETE FROM local_credentials
            WHERE identity_id = :id
            """
        ),
        {"id": int(identity_id)},
    )
    db.execute(
        text(
            """
            DELETE FROM identities
            WHERE id = :id
            """
        ),
        {"id": int(identity_id)},
    )
    db.commit()

    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="identity.account_deleted",
        outcome="success",
        target_type="identity",
        target_id=int(identity_id),
        target_display=str(user_row.get("display_name") or user_row.get("username") or identity_id),
        context_json={"identity_type": str(user_row.get("type") or "user").lower(), "deleted": True},
        correlation_id=correlation_id,
    )

    return ui_data(
        {"id": int(identity_id), "type": str(user_row.get("type") or "user").lower(), "deleted": True},
        meta={"identity_id": int(identity_id), "identity_type": str(user_row.get("type") or "user").lower(), "deleted": True},
    )


@router.post("/search")
async def search_identity_overview(
    _payload: IdentitySearchRequest,
):
    _moved_to_governance(
        error_code="IDENTITY_SEARCH_MOVED_TO_GOVERNANCE",
        message="Identity search is orchestrated by governance and active snapshots.",
    )


@router.patch("/{identity_id}")
async def update_identity(
    identity_id: int,
    request: Request,
    payload: dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
):
    identity_type = _normalize_identity_type(payload.get("identity_type"))
    display_name = payload.get("display_name")
    is_active = payload.get("is_active")
    application_role = _normalize_app_role(payload.get("application_role"))

    if payload.get("application_role") is not None and not application_role:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="application_role must be one of: user, platform_admin",
        )

    if identity_type == "group" and is_active is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="is_active is not supported for directory groups",
        )

    updates: list[str] = []
    params: dict[str, Any] = {"id": int(identity_id)}
    group_updates: list[str] = []
    group_params: dict[str, Any] = {"id": int(identity_id)}

    if display_name is not None:
        next_display_name = str(display_name).strip() or None
        if identity_type == "group":
            group_updates.append("name = :display_name")
            group_params["display_name"] = next_display_name
        else:
            updates.append("display_name = :display_name")
            params["display_name"] = next_display_name

    if is_active is not None:
        updates.append("is_active = :is_active")
        params["is_active"] = 1 if bool(is_active) else 0
        updates.append("status = :status")
        params["status"] = "active" if bool(is_active) else "inactive"

    if not updates and not group_updates and application_role is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No supported fields provided")

    subject_type = identity_type or "user"
    if subject_type == "group":
        before_row = db.execute(
            text(
                """
                SELECT
                  dg.id,
                  dg.name AS display_name,
                  NULL AS username,
                  NULL AS is_active,
                  'group' AS type,
                  'ad' AS auth_source
                FROM directory_groups dg
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": int(identity_id)},
        ).mappings().first()
    else:
        before_row = db.execute(
            text(
                """
                SELECT id, username, display_name, is_active, type, auth_source
                FROM identities
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": int(identity_id)},
        ).mappings().first()
        if before_row:
            subject_type = str(before_row.get("type") or "user").strip().lower() or "user"

    if not before_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity not found")

    if subject_type == "group":
        if group_updates:
            group_updates.append("updated_at = NOW(6)")
            db.execute(
                text(
                    f"""
                    UPDATE directory_groups
                    SET {", ".join(group_updates)}
                    WHERE id = :id
                    """
                ),
                group_params,
            )
        if application_role is not None:
            _set_subject_application_role(
                db=db,
                identity_id=None,
                directory_group_id=int(identity_id),
                role_code=application_role,
            )
    else:
        if updates or application_role is not None:
            updates.append("updated_at = NOW(6)")
            db.execute(
                text(
                    f"""
                    UPDATE identities
                    SET {", ".join(updates)}
                    WHERE id = :id
                    """
                ),
                params,
            )
        if application_role is not None:
            _set_subject_application_role(
                db=db,
                identity_id=int(identity_id),
                directory_group_id=None,
                role_code=application_role,
            )

    db.commit()

    if subject_type == "group":
        row = db.execute(
            text(
                """
                SELECT
                  dg.id,
                  'group' AS type,
                  dg.name AS username,
                  dg.name AS display_name,
                  NULL AS email,
                  'ad' AS auth_source,
                  dg.external_id,
                  dg.identity_source_id AS source_id,
                  NULL AS is_active
                FROM directory_groups dg
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": int(identity_id)},
        ).mappings().first()
    else:
        row = db.execute(
            text(
                """
                SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type
                FROM identities
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": int(identity_id)},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity not found")

    actor_id, actor_display = _actor_from_headers(request)
    target_display = str(row.get("display_name") or row.get("username") or row.get("id"))
    correlation_id = request.headers.get("x-request-id") or None

    before_display_name = str(before_row.get("display_name") or "").strip() or None
    after_display_name = str(row.get("display_name") or "").strip() or None
    before_active = bool(before_row.get("is_active")) if before_row.get("is_active") is not None else None
    after_active = bool(row.get("is_active")) if row.get("is_active") is not None else None
    target_type = "identity_group" if subject_type == "group" else "identity"

    if before_display_name != after_display_name:
        log_activity(
            db,
            actor_type="user" if actor_id is not None else "system",
            actor_id=actor_id,
            actor_display=actor_display,
            action="identity.account_renamed",
            outcome="success",
            target_type=target_type,
            target_id=int(identity_id),
            target_display=target_display,
            context_json={
                "before": {"display_name": before_display_name},
                "after": {"display_name": after_display_name},
                "updated_fields": ["display_name"],
            },
            correlation_id=correlation_id,
        )

    if before_active is not None and after_active is not None and before_active != after_active:
        log_activity(
            db,
            actor_type="user" if actor_id is not None else "system",
            actor_id=actor_id,
            actor_display=actor_display,
            action="identity.account_enabled" if after_active else "identity.account_disabled",
            outcome="success",
            target_type=target_type,
            target_id=int(identity_id),
            target_display=target_display,
            context_json={
                "before": {"is_active": before_active},
                "after": {"is_active": after_active},
                "updated_fields": ["is_active"],
            },
            correlation_id=correlation_id,
        )

    if application_role is not None:
        log_activity(
            db,
            actor_type="user" if actor_id is not None else "system",
            actor_id=actor_id,
            actor_display=actor_display,
            action="identity.application_role_updated",
            outcome="success",
            target_type=target_type,
            target_id=int(identity_id),
            target_display=target_display,
            context_json={"application_role": application_role},
            correlation_id=correlation_id,
        )

    return ui_data(
        {
            "id": row.get("id"),
            "type": str(row.get("type") or "user").lower(),
            "username": row.get("username"),
            "display_name": row.get("display_name"),
            "email": row.get("email"),
            "auth_source": row.get("auth_source"),
            "external_id": row.get("external_id"),
            "identity_source_id": row.get("source_id"),
            "is_active": bool(row.get("is_active")) if row.get("is_active") is not None else None,
            "application_role": application_role,
        },
        meta={"identity_id": int(identity_id), "identity_type": subject_type},
    )


@router.post("/import/ad")
async def import_identity_ad(
    _payload: dict[str, Any] = Body(default={}),
):
    _moved_to_governance(
        error_code="IDENTITY_IMPORT_MOVED_TO_GOVERNANCE",
        message="Identity import is orchestrated asynchronously by governance jobs.",
    )


@router.post("/import/ad/batch")
async def import_identity_ad_batch(
    _payload: dict[str, Any] = Body(default={}),
):
    _moved_to_governance(
        error_code="IDENTITY_IMPORT_BATCH_MOVED_TO_GOVERNANCE",
        message="Batch identity import is orchestrated asynchronously by governance jobs.",
    )
