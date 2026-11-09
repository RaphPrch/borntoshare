from __future__ import annotations

from typing import Any

import logging
import os
import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.services.identity_source_fields import source_capabilities
from app.services.identity_bindings import sync_identity_bindings
from app.core.db import get_db
from app.data.models.identity_sources import IdentitySource
from app.api.internal_auth_local import _hash_b2s_password
from app.api._helpers import ui_data, ui_list
from app.schemas.identity_search import IdentitySearchRequest
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request, admin_or_internal


logger = logging.getLogger("core.identity")

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


def _other_admin_exists(db: Session, *, excluding_identity: int | None = None, excluding_group: int | None = None) -> bool:
    """Someone else keeps the platform administrator role: an active person, or a directory group that holds it."""
    row = db.execute(
        text(
            """
            SELECT 1
            FROM identity_roles ir
            JOIN roles r ON r.id = ir.role_id AND r.code = 'platform_admin'
            LEFT JOIN identities i ON i.id = ir.identity_id
            WHERE (ir.identity_id IS NOT NULL AND i.is_active = 1 AND ir.identity_id <> COALESCE(:identity, 0))
               OR (ir.directory_group_id IS NOT NULL AND ir.directory_group_id <> COALESCE(:grp, 0))
            LIMIT 1
            """
        ),
        {"identity": excluding_identity, "grp": excluding_group},
    ).first()
    return row is not None


def _subject_is_admin(db: Session, *, identity_id: int | None = None, group_id: int | None = None) -> bool:
    return db.execute(
        text(
            """
            SELECT 1 FROM identity_roles ir JOIN roles r ON r.id = ir.role_id AND r.code = 'platform_admin'
            WHERE (:identity IS NOT NULL AND ir.identity_id = :identity) OR (:grp IS NOT NULL AND ir.directory_group_id = :grp)
            LIMIT 1
            """
        ),
        {"identity": identity_id, "grp": group_id},
    ).first() is not None


def _is_last_local_admin(db: Session, identity_id: int) -> bool:
    """The only active local account holding the administrator role (the fallback when the directory is down)."""
    rows = db.execute(
        text(
            """
            SELECT i.id FROM identity_roles ir JOIN roles r ON r.id = ir.role_id AND r.code = 'platform_admin'
            JOIN identities i ON i.id = ir.identity_id
            WHERE LOWER(i.auth_source) = 'local' AND i.is_active = 1
            """
        )
    ).all()
    ids = {int(row[0]) for row in rows}
    return ids == {int(identity_id)}


def _orphaned_folders(db: Session, identity_id: int) -> list[dict[str, Any]]:
    """Folders this person guards with no other active guardian: they would be left without anyone to validate."""
    rows = db.execute(
        text(
            """
            SELECT sr.id, sr.name, sr.root_path
            FROM storage_root_roles r JOIN storage_roots sr ON sr.id = r.root_id
            WHERE r.identity_id = :id AND LOWER(r.role) = 'guardian'
              AND NOT EXISTS (
                SELECT 1 FROM storage_root_roles o JOIN identities oi ON oi.id = o.identity_id
                WHERE o.root_id = r.root_id AND LOWER(o.role) = 'guardian' AND o.identity_id <> :id AND oi.is_active = 1
              )
            ORDER BY sr.root_path
            """
        ),
        {"id": int(identity_id)},
    ).mappings().all()
    return [{"id": int(row["id"]), "name": row["name"], "path": row["root_path"]} for row in rows]


def _refuse_guardian_gap(db: Session, request: Request, *, action: str, identity_id: int) -> None:
    """Removing or disabling the only active guardian of a folder is refused: hand the folders over first."""
    folders = _orphaned_folders(db, identity_id)
    if not folders:
        return
    actor_id, actor_display = _actor_from_headers(request)
    log_activity(
        db, actor_type="user" if actor_id is not None else "system", actor_id=actor_id, actor_display=actor_display,
        action=action, outcome="denied", target_type="identity", target_id=int(identity_id),
        context_json={"code": "GUARDIAN_HANDOVER_REQUIRED", "folders": [f["id"] for f in folders[:50]]},
        correlation_id=request.headers.get("x-request-id") or None,
    )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "GUARDIAN_HANDOVER_REQUIRED",
                "message": f"Seul gardien actif de {len(folders)} dossier(s) : confiez-les à quelqu'un d'autre d'abord."},
    )


def _refuse_admin_loss(
    db: Session,
    request: Request,
    *,
    action: str,
    identity_id: int | None = None,
    group_id: int | None = None,
) -> None:
    """Nobody removes their own account or rights, and the platform always keeps one administrator."""
    actor_id, actor_display = _actor_from_headers(request)
    code = message = None
    if identity_id is not None and actor_id is not None and int(identity_id) == int(actor_id):
        code, message = "IDENTITY_SELF_CHANGE_FORBIDDEN", "Vous ne pouvez pas supprimer, désactiver ou rétrograder votre propre compte."
    elif _subject_is_admin(db, identity_id=identity_id, group_id=group_id) and not _other_admin_exists(
        db, excluding_identity=identity_id, excluding_group=group_id
    ):
        code, message = "LAST_ADMIN_FORBIDDEN", "La plateforme doit garder au moins un administrateur."
    elif identity_id is not None and _is_last_local_admin(db, int(identity_id)):
        code, message = (
            "LAST_LOCAL_ADMIN_FORBIDDEN",
            "Gardez au moins un administrateur local actif : c'est l'accès de secours quand l'annuaire ne répond plus.",
        )
    if not code:
        return
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action=action,
        outcome="denied",
        target_type="identity_group" if group_id is not None else "identity",
        target_id=int(group_id if group_id is not None else identity_id),
        context_json={"code": code},
        correlation_id=request.headers.get("x-request-id") or None,
    )
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": code, "message": message})


def _close_sessions(identity_id: int) -> None:
    """The account can no longer act: its open sessions end now (best effort, logged by the auth service)."""
    try:
        url = (os.getenv("B2S_AUTH_URL") or "http://auth-service:8000").rstrip("/") + "/auth/internal/sessions/revoke"
        httpx.post(url, json={"identity_id": str(identity_id)}, headers={"X-Internal-Token": os.getenv("INTERNAL_TOKEN") or ""}, timeout=3.0)
    except httpx.HTTPError:
        logger.warning("IDENTITY_SESSIONS_NOT_CLOSED", extra={"identity_id": identity_id})


def _refuse_outside_directory(identity_source: Any, dn: str | None) -> None:
    base_dn = _clean_text(getattr(identity_source, "base_dn", None))
    if base_dn and (not dn or not dn.lower().replace(", ", ",").endswith(base_dn.lower().replace(", ", ","))):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "OUTSIDE_DIRECTORY", "message": "Cet objet n'appartient pas à cet annuaire."},
        )


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


@router.get("", dependencies=[Depends(admin_or_internal)])
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


@router.post("", dependencies=[Depends(admin_or_internal)])
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
        if len(password) < 12:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "PASSWORD_TOO_SHORT", "message": "Le mot de passe d'un compte local fait au moins 12 caractères."},
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
        # An object outside the directory would become a false entry, and nobody could ever be matched with it
        _refuse_outside_directory(identity_source, _clean_text(principal.get("dn")))
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
        # Link to the directory user of the snapshot (group roles, effective access)
        sync_identity_bindings(db, identity_id=target_id)

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

        if not bool(source_capabilities(identity_source).get("import_groups", True)):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Importing groups is disabled for this identity source",
            )

        external_id = _clean_text(principal.get("external_id")) or _clean_text(principal.get("dn")) or _clean_text(principal.get("username"))
        display_name = _clean_text(principal.get("display_name")) or _clean_text(principal.get("name")) or external_id
        dn = _clean_text(principal.get("dn"))
        # An object outside the directory would become a false entry, and nobody could ever be matched with it
        _refuse_outside_directory(identity_source, dn)
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


@router.get("/groups/{group_id}/members", dependencies=[Depends(admin_or_internal)])
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
              du.email
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
            }
            for row in rows
        ],
        meta={"group_id": int(group_id), "count": len(rows)},
    )


@router.delete("/{identity_id}", dependencies=[Depends(admin_or_internal)])
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

        _refuse_admin_loss(db, request, action="identity.group_access_revoked", group_id=int(identity_id))
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
            _refuse_admin_loss(db, request, action="identity.group_access_revoked", group_id=int(identity_id))
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
    _refuse_admin_loss(db, request, action="identity.account_deleted", identity_id=int(identity_id))
    _refuse_guardian_gap(db, request, action="identity.account_deleted", identity_id=int(identity_id))

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
    _close_sessions(int(identity_id))

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


@router.patch("/{identity_id}", dependencies=[Depends(admin_or_internal)])
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
    loses_admin = application_role is not None and application_role != "platform_admin"
    if subject_type == "group" and loses_admin:
        _refuse_admin_loss(db, request, action="identity.application_role_updated", group_id=int(identity_id))
    elif subject_type != "group" and (loses_admin or is_active is False):
        _refuse_admin_loss(db, request, action="identity.application_role_updated", identity_id=int(identity_id))
    if subject_type != "group" and is_active is False:
        _refuse_guardian_gap(db, request, action="identity.application_role_updated", identity_id=int(identity_id))
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
    if subject_type != "group" and (loses_admin or is_active is False):
        _close_sessions(int(identity_id))

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


@router.get("/{identity_id}/handover", dependencies=[Depends(admin_or_internal)])
def get_handover_needs(identity_id: int, db: Session = Depends(get_db)):
    """What a deletion or a deactivation would leave without guardian (asked before showing the confirmation)."""
    return ui_data({"orphaned": _orphaned_folders(db, int(identity_id))})


@router.post("/{identity_id}/handover", dependencies=[Depends(admin_or_internal)])
def hand_over_guardianship(identity_id: int, request: Request, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    """Make another person guardian of the folders of this one (all of them, or only those left without guardian),
    and optionally take this one off them (before a deletion)."""
    to_id = int(payload.get("to_identity_id") or 0)
    scope = str(payload.get("scope") or "all")
    remove = bool(payload.get("remove_from_source"))
    if to_id <= 0 or to_id == int(identity_id):
        raise HTTPException(status_code=422, detail={"code": "HANDOVER_TARGET_INVALID", "message": "Choisissez une autre personne."})
    target = db.execute(text("SELECT id, is_active, type FROM identities WHERE id = :id"), {"id": to_id}).mappings().first()
    if target is None or not target["is_active"] or str(target["type"]) == "group":
        raise HTTPException(status_code=422, detail={"code": "HANDOVER_TARGET_INVALID", "message": "La personne choisie doit être active."})
    folder_ids = [f["id"] for f in _orphaned_folders(db, int(identity_id))] if scope == "orphaned" else [
        int(row[0]) for row in db.execute(
            text("SELECT root_id FROM storage_root_roles WHERE identity_id = :id AND LOWER(role) = 'guardian'"), {"id": int(identity_id)}
        ).all()
    ]
    actor_id, actor_display = _actor_from_headers(request)
    added = 0
    for root_id in folder_ids:
        exists = db.execute(
            text("SELECT 1 FROM storage_root_roles WHERE root_id = :root AND identity_id = :to AND LOWER(role) = 'guardian'"), {"root": root_id, "to": to_id}
        ).first()
        if not exists:
            db.execute(
                text("INSERT INTO storage_root_roles (root_id, identity_id, role, assigned_by, assigned_at) VALUES (:root, :to, 'guardian', :by, NOW())"),
                {"root": root_id, "to": to_id, "by": actor_id},
            )
            added += 1
    removed = 0
    if remove and folder_ids:
        removed = db.execute(
            text("DELETE FROM storage_root_roles WHERE identity_id = :id AND LOWER(role) = 'guardian' AND root_id IN :roots")
            .bindparams(bindparam("roots", expanding=True)),
            {"id": int(identity_id), "roots": folder_ids},
        ).rowcount
    db.commit()
    log_activity(
        db, actor_type="user" if actor_id is not None else "system", actor_id=actor_id, actor_display=actor_display,
        action="identity.guardianship_handed_over", outcome="success", target_type="identity", target_id=int(identity_id),
        context_json={"to_identity_id": to_id, "folders": len(folder_ids), "added": added, "removed": int(removed or 0), "scope": scope},
        correlation_id=request.headers.get("x-request-id") or None,
    )
    return ui_data({"folders": len(folder_ids), "added": added, "removed": int(removed or 0)})


def _substitute_rows(db: Session, where: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            f"""
            SELECT gs.id, gs.identity_id, gs.substitute_identity_id, gs.starts_at, gs.ends_at, gs.reason, gs.created_by,
              COALESCE(NULLIF(g.display_name, ''), g.username) AS guardian_name,
              COALESCE(NULLIF(s.display_name, ''), s.username) AS substitute_name, s.email AS substitute_email,
              CASE WHEN gs.starts_at > UTC_TIMESTAMP() THEN 'upcoming' WHEN gs.ends_at > UTC_TIMESTAMP() THEN 'active' ELSE 'past' END AS state
            FROM guardian_substitutes gs
            JOIN identities g ON g.id = gs.identity_id JOIN identities s ON s.id = gs.substitute_identity_id
            WHERE gs.revoked_at IS NULL AND gs.ends_at > UTC_TIMESTAMP() - INTERVAL 30 DAY AND {where}
            ORDER BY gs.starts_at
            """
        ),
        params,
    ).mappings().all()
    iso = lambda value: value.isoformat() + "Z" if value else None  # noqa: E731
    return [{**dict(row), "starts_at": iso(row["starts_at"]), "ends_at": iso(row["ends_at"])} for row in rows]


@router.get("/{identity_id}/substitutes", dependencies=[Depends(admin_or_internal)])
def list_substitutes(identity_id: int, db: Session = Depends(get_db)):
    """Backup guardians of this person (current, upcoming and of the last 30 days), and those they ensure."""
    return ui_data({
        "for_them": _substitute_rows(db, "gs.identity_id = :id", {"id": int(identity_id)}),
        "by_them": _substitute_rows(db, "gs.substitute_identity_id = :id", {"id": int(identity_id)}),
    })


@router.post("/{identity_id}/substitutes", status_code=status.HTTP_201_CREATED, dependencies=[Depends(admin_or_internal)])
def create_substitute(identity_id: int, request: Request, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    """During an absence, another person validates the requests of all the folders of this guardian."""
    from datetime import date, datetime, timedelta

    def refuse(code: str, message: str, http: int = 422):
        raise HTTPException(status_code=http, detail={"code": code, "message": message})

    substitute_id = int(payload.get("substitute_identity_id") or 0)
    try:
        start = date.fromisoformat(str(payload.get("starts_on") or ""))
        end = date.fromisoformat(str(payload.get("ends_on") or ""))
    except ValueError:
        refuse("SUBSTITUTE_DATES_INVALID", "Indiquez les dates de début et de fin.")
    if end < start:
        refuse("SUBSTITUTE_DATES_INVALID", "La fin vient après le début.")
    if (end - start).days > 365:
        refuse("SUBSTITUTE_TOO_LONG", "Une suppléance dure au plus un an : au-delà, confiez les dossiers.")
    if end < date.today():
        refuse("SUBSTITUTE_DATES_INVALID", "Cette période est déjà passée.")
    guardian = db.execute(text("SELECT id FROM identities WHERE id = :id"), {"id": int(identity_id)}).first()
    if guardian is None:
        raise HTTPException(status_code=404, detail="Identity not found")
    if not db.execute(text("SELECT 1 FROM storage_root_roles WHERE identity_id = :id AND LOWER(role) = 'guardian' LIMIT 1"), {"id": int(identity_id)}).first():
        refuse("SUBSTITUTE_NOT_A_GUARDIAN", "Cette personne ne garde aucun dossier.")
    target = db.execute(text("SELECT id, is_active, type FROM identities WHERE id = :id"), {"id": substitute_id}).mappings().first()
    if target is None or substitute_id == int(identity_id) or not target["is_active"] or str(target["type"]) == "group":
        refuse("SUBSTITUTE_INVALID", "Choisissez une autre personne, active.")
    # Times in UTC: from the first day 00:00 to the day after the last one 00:00
    starts_at = datetime.combine(start, datetime.min.time())
    ends_at = datetime.combine(end + timedelta(days=1), datetime.min.time())
    overlap = db.execute(
        text(
            """
            SELECT 1 FROM guardian_substitutes WHERE identity_id = :id AND revoked_at IS NULL
              AND starts_at < :ends AND ends_at > :starts LIMIT 1
            """
        ),
        {"id": int(identity_id), "starts": starts_at, "ends": ends_at},
    ).first()
    if overlap:
        refuse("SUBSTITUTE_OVERLAP", "Une suppléance couvre déjà une partie de cette période.", 409)
    actor_id, actor_display = _actor_from_headers(request)
    result = db.execute(
        text(
            """
            INSERT INTO guardian_substitutes (identity_id, substitute_identity_id, starts_at, ends_at, reason, created_by)
            VALUES (:id, :sub, :starts, :ends, :reason, :by)
            """
        ),
        {"id": int(identity_id), "sub": substitute_id, "starts": starts_at, "ends": ends_at,
         "reason": (str(payload.get("reason") or "").strip()[:300] or None), "by": actor_display},
    )
    db.commit()
    log_activity(
        db, actor_type="user" if actor_id is not None else "system", actor_id=actor_id, actor_display=actor_display,
        action="identity.substitute_set", outcome="success", target_type="identity", target_id=int(identity_id),
        context_json={"substitute_identity_id": substitute_id, "starts_on": start.isoformat(), "ends_on": end.isoformat(), "reason": payload.get("reason")},
        correlation_id=request.headers.get("x-request-id") or None,
    )
    return ui_data({"id": int(result.lastrowid)})


@router.delete("/substitutes/{substitute_id}", dependencies=[Depends(admin_or_internal)])
def revoke_substitute(substitute_id: int, request: Request, db: Session = Depends(get_db)):
    actor_id, actor_display = _actor_from_headers(request)
    row = db.execute(text("SELECT identity_id FROM guardian_substitutes WHERE id = :id AND revoked_at IS NULL"), {"id": int(substitute_id)}).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Substitution not found")
    db.execute(text("UPDATE guardian_substitutes SET revoked_at = UTC_TIMESTAMP(), revoked_by = :by WHERE id = :id"), {"id": int(substitute_id), "by": actor_display})
    db.commit()
    log_activity(
        db, actor_type="user" if actor_id is not None else "system", actor_id=actor_id, actor_display=actor_display,
        action="identity.substitute_revoked", outcome="success", target_type="identity", target_id=int(row[0]),
        context_json={"substitution_id": int(substitute_id)}, correlation_id=request.headers.get("x-request-id") or None,
    )
    return ui_data({"revoked": int(substitute_id)})


@router.get("/guardians", dependencies=[Depends(admin_or_internal)])
def list_guardian_counts(db: Session = Depends(get_db)):
    """Folders guarded per identity, and those where it is the only guardian (list of the Identities page)."""
    rows = db.execute(
        text(
            """
            SELECT r.identity_id, COUNT(*) AS folders,
              SUM(NOT EXISTS (SELECT 1 FROM storage_root_roles o WHERE o.root_id = r.root_id AND LOWER(o.role) = 'guardian'
                              AND o.identity_id <> r.identity_id)) AS sole
            FROM storage_root_roles r WHERE LOWER(r.role) = 'guardian' AND r.identity_id IS NOT NULL
            GROUP BY r.identity_id
            """
        )
    ).mappings().all()
    return ui_list([{"identity_id": int(r["identity_id"]), "folders": int(r["folders"]), "sole": int(r["sole"] or 0)} for r in rows])


@router.get("/admins", dependencies=[Depends(admin_or_internal)])
def list_platform_admins(db: Session = Depends(get_db)):
    """Every path to the platform administrator role (local account, directory account, directory group), who takes
    it, and what deserves a look: a role held both directly and through a group, several local administrators."""
    direct = [dict(r) for r in db.execute(
        text(
            """
            SELECT i.id, i.username, COALESCE(NULLIF(i.display_name, ''), i.username) AS name, i.email, i.auth_source,
              i.is_active, s.name AS source_name
            FROM identity_roles ir JOIN roles r ON r.id = ir.role_id AND r.code = 'platform_admin'
            JOIN identities i ON i.id = ir.identity_id LEFT JOIN identity_sources s ON s.id = i.source_id
            WHERE ir.identity_id IS NOT NULL ORDER BY i.auth_source DESC, name
            """
        )
    ).mappings().all()]
    groups = []
    for g in db.execute(
        text(
            """
            SELECT g.id, g.name, g.dn, s.name AS source_name
            FROM identity_roles ir JOIN roles r ON r.id = ir.role_id AND r.code = 'platform_admin'
            JOIN directory_groups g ON g.id = ir.directory_group_id LEFT JOIN identity_sources s ON s.id = g.identity_source_id
            WHERE ir.directory_group_id IS NOT NULL ORDER BY g.name
            """
        )
    ).mappings().all():
        members = [dict(m) for m in db.execute(
            text(
                """
                SELECT DISTINCT i.id, i.username, COALESCE(NULLIF(i.display_name, ''), i.username) AS name, i.is_active
                FROM directory_effective_memberships dem
                JOIN identity_bindings ib ON ib.directory_user_id = dem.directory_user_id AND ib.deleted_at IS NULL
                JOIN identities i ON i.id = ib.identity_id
                WHERE dem.directory_group_id = :gid ORDER BY name
                """
            ),
            {"gid": int(g["id"])},
        ).mappings().all()]
        directory_members = db.execute(
            text("SELECT COUNT(DISTINCT directory_user_id) FROM directory_effective_memberships WHERE directory_group_id = :gid"), {"gid": int(g["id"])}
        ).scalar() or 0
        groups.append({**dict(g), "members": members, "directory_members": int(directory_members)})
    effective = db.execute(
        # A disabled account cannot sign in: it is no administrator, whatever role it keeps
        text(
            "SELECT COUNT(DISTINCT v.identity_id) FROM v_identity_effective_roles v JOIN identities i ON i.id = v.identity_id"
            " WHERE v.role_code = 'platform_admin' AND i.is_active = 1"
        )
    ).scalar() or 0
    through_group = {m["id"] for g in groups for m in g["members"]}
    issues = []
    for person in direct:
        if person["auth_source"] != "local" and person["id"] in through_group:
            issues.append({"code": "DIRECT_AND_GROUP", "identity_id": person["id"], "name": person["name"]})
    locals_ = [p for p in direct if p["auth_source"] == "local" and p["is_active"]]
    if len(locals_) > 1:
        issues.append({"code": "SEVERAL_LOCAL_ADMINS", "identities": [{"id": p["id"], "name": p["name"]} for p in locals_]})
    for person in direct:
        person["is_active"] = bool(person["is_active"])
    return ui_data({"direct": direct, "groups": groups, "effective": int(effective), "issues": issues})


@router.get("/{identity_id}/overview", dependencies=[Depends(admin_or_internal)])
def get_identity_overview(identity_id: int, db: Session = Depends(get_db)):
    """The page of a person: roles and how they are held, folders guarded (with co-guardians), requests."""
    row = db.execute(
        text(
            """
            SELECT i.id, i.type, i.username, i.display_name, i.email, i.auth_source, i.external_id, i.is_active, i.status,
              i.created_at, i.updated_at, i.source_id, s.name AS source_name,
              (SELECT du.dn FROM directory_users du WHERE du.identity_source_id = i.source_id
                 AND (du.external_id = i.external_id OR LOWER(du.username) = LOWER(i.username)) ORDER BY du.id DESC LIMIT 1) AS dn
            FROM identities i LEFT JOIN identity_sources s ON s.id = i.source_id
            WHERE i.id = :id
            """
        ),
        {"id": int(identity_id)},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity not found")
    roles = [dict(r) for r in db.execute(
        text("SELECT DISTINCT role_code AS code, via FROM v_identity_effective_roles WHERE identity_id = :id"), {"id": int(identity_id)}
    ).mappings().all()]
    guarded = db.execute(
        text(
            """
            SELECT sr.id, sr.name, sr.root_path,
              (SELECT GROUP_CONCAT(COALESCE(NULLIF(o.display_name, ''), o.username) ORDER BY o.username SEPARATOR '|')
                 FROM storage_root_roles x JOIN identities o ON o.id = x.identity_id
                 WHERE x.root_id = sr.id AND LOWER(x.role) = 'guardian' AND x.identity_id <> :id) AS others,
              (SELECT GROUP_CONCAT(x.identity_id) FROM storage_root_roles x
                 WHERE x.root_id = sr.id AND LOWER(x.role) = 'guardian' AND x.identity_id <> :id) AS other_ids
            FROM storage_root_roles r JOIN storage_roots sr ON sr.id = r.root_id
            WHERE r.identity_id = :id AND LOWER(r.role) = 'guardian'
            ORDER BY sr.root_path
            """
        ),
        {"id": int(identity_id)},
    ).mappings().all()
    folders = []
    partners: dict[int, dict[str, Any]] = {}
    for item in guarded:
        others = [name for name in str(item["others"] or "").split("|") if name]
        other_ids = [int(value) for value in str(item["other_ids"] or "").split(",") if value]
        parts = [part for part in str(item["root_path"] or "").replace("/", "\\").split("\\") if part]
        folders.append({"id": int(item["id"]), "name": item["name"], "path": item["root_path"], "share": parts[1] if len(parts) > 1 else "",
                        "co_guardians": others, "sole": not others})
        for other_id, name in zip(other_ids, others):
            partners.setdefault(other_id, {"id": other_id, "name": name, "shared": 0})["shared"] += 1
    if partners:
        mails = dict(db.execute(
            text("SELECT id, email FROM identities WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)), {"ids": list(partners)}
        ).all())
        for partner in partners.values():
            partner["has_email"] = bool(mails.get(partner["id"]))
    requests = {str(s): int(c) for s, c in db.execute(
        text("SELECT LOWER(status), COUNT(*) FROM access_requests WHERE requester_identity_id = :id GROUP BY LOWER(status)"), {"id": int(identity_id)}
    ).all()}
    iso = lambda value: value.isoformat() + "Z" if value else None  # noqa: E731
    return ui_data({
        **{k: row[k] for k in ("id", "type", "username", "display_name", "email", "auth_source", "external_id", "status", "source_id", "source_name", "dn")},
        "is_active": bool(row["is_active"]),
        "created_at": iso(row["created_at"]),
        "updated_at": iso(row["updated_at"]),
        "roles": roles,
        "guarded": folders,
        "co_guardians": sorted(partners.values(), key=lambda p: -p["shared"]),
        "requests": requests,
        "active_accesses": sum(requests.get(s, 0) for s in ("approved", "applied", "active")),
    })
