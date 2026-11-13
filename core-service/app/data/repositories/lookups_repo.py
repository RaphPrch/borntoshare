"""Small reads the routes need (one object by id, a count, a state): the routes hold no SQL themselves."""
from __future__ import annotations

from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


def storage_root(db: Session, root_id: int):
    from app.data.models.storage_root import StorageRoot

    return db.get(StorageRoot, int(root_id))


def identity_source(db: Session, source_id: int):
    from app.data.models.identity_sources import IdentitySource

    return db.get(IdentitySource, int(source_id))


def sensitivity_scanned_at(db: Session, root_ids: list[int]) -> dict[int, Any]:
    """{folder: last sensitivity scan}."""
    if not root_ids:
        return {}
    rows = db.execute(text("SELECT storage_root_id, scanned_at FROM storage_root_sensitivity WHERE scanned_at IS NOT NULL AND storage_root_id IN :ids")
                      .bindparams(bindparam("ids", expanding=True)), {"ids": list(root_ids)}).all()
    return {int(root): at for root, at in rows}


def folders_with_open_alerts(db: Session, root_ids: list[int]) -> int:
    """How many of these folders have an open alert (the pending validations aside)."""
    if not root_ids:
        return 0
    return int(db.execute(text("SELECT COUNT(DISTINCT storage_root_id) FROM governance_alerts "
                               "WHERE status = 'open' AND storage_root_id IN :ids AND alert_type <> 'pending_access_validation'")
                          .bindparams(bindparam("ids", expanding=True)), {"ids": sorted(root_ids)}).scalar() or 0)


def enabled_sso_providers(db: Session) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(text("SELECT id, name, button_label FROM sso_providers WHERE is_enabled = 1 ORDER BY name")).mappings()]


def folder_task_state(db: Session, kind: str, root_id: int) -> dict[str, Any] | None:
    """The state of the measure (kind « measure ») or sensitivity scan of a folder: {status, job_id}."""
    table = "storage_root_sensitivity" if kind == "sensitivity" else "storage_root_scans"
    row = db.execute(text(f"SELECT status, job_id FROM {table} WHERE storage_root_id = :id"), {"id": int(root_id)}).mappings().first()
    return dict(row) if row else None


# ---- identity sources offered at sign-in (columns read as the schema has them) ----
from sqlalchemy.orm import load_only  # noqa: E402

from app.data.models.identity_sources import IdentitySource  # noqa: E402
from app.services.identity_source_fields import identity_source_columns, source_auth_enabled  # noqa: E402


def _source_is_active(src: IdentitySource) -> bool:
    if "is_active" in src.__dict__:
        return bool(src.__dict__.get("is_active"))
    status = str(src.__dict__.get("status") or "").strip().lower()
    if status:
        return status == "active"
    return True


def auth_identity_sources(db: Session, source_type: str) -> list[IdentitySource]:
    available = identity_source_columns(db)
    query = db.query(IdentitySource)
    if available:
        attrs = [
            getattr(IdentitySource, col.name)
            for col in IdentitySource.__table__.columns
            if col.name in available
        ]
        if attrs:
            query = query.options(load_only(*attrs))

    query = query.filter(IdentitySource.type == source_type)
    if "is_active" in available:
        query = query.filter(IdentitySource.is_active.is_(True))
    if "auth_enabled" in available:
        query = query.filter(IdentitySource.auth_enabled.is_(True))
    if "auth_priority" in available:
        query = query.order_by(IdentitySource.auth_priority.asc(), IdentitySource.id.desc())
    else:
        query = query.order_by(IdentitySource.id.desc())

    rows = query.all()
    if "is_active" not in available:
        rows = [row for row in rows if _source_is_active(row)]
    if "auth_enabled" not in available:
        rows = [row for row in rows if source_auth_enabled(row)]
    return rows
