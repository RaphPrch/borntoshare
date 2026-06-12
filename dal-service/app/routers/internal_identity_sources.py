from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect
from sqlalchemy.orm import load_only
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.logging import get_logger
from app.security.internal_auth import require_internal
from app.models.identity_sources import IdentitySource

router = APIRouter(
    prefix="/internal/identity-sources",
    tags=["internal-identity-sources"],
    dependencies=[require_internal({"jobs:read"})],
)
logger = get_logger("dal-identity-sources")


def _identity_source_available_columns(db: Session) -> set[str]:
    try:
        inspector = inspect(db.get_bind())
        return {col["name"] for col in inspector.get_columns(IdentitySource.__tablename__)}
    except Exception:
        return set()


def _source_capabilities(src: IdentitySource) -> dict[str, object]:
    raw = src.__dict__.get("capabilities")
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _source_auth_enabled(src: IdentitySource, caps: dict[str, object] | None = None) -> bool:
    if "auth_enabled" in src.__dict__:
        return bool(src.__dict__.get("auth_enabled"))
    effective_caps = caps if isinstance(caps, dict) else _source_capabilities(src)
    return bool(effective_caps.get("auth", False))


def _source_auth_priority(src: IdentitySource) -> int:
    if "auth_priority" in src.__dict__:
        raw = src.__dict__.get("auth_priority")
        try:
            return int(raw or 100)
        except Exception:
            return 100
    return 100


def _source_is_active(src: IdentitySource) -> bool:
    if "is_active" in src.__dict__:
        return bool(src.__dict__.get("is_active"))
    status = str(src.__dict__.get("status") or "").strip().lower()
    if status:
        return status == "active"
    return True


def _query_identity_sources(db: Session, source_type: str) -> list[IdentitySource]:
    available = _identity_source_available_columns(db)
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
        rows = [row for row in rows if _source_auth_enabled(row)]
    return rows


def _norm_domain(value: str | None) -> str:
    return str(value or "").strip().lower().strip(".")


def _domain_aliases(value: str | None) -> set[str]:
    norm = _norm_domain(value)
    if not norm:
        return set()
    aliases = {norm}
    if "." in norm:
        aliases.add(norm.split(".", 1)[0])
    return aliases


def _to_payload(src: IdentitySource) -> dict:
    caps = _source_capabilities(src)
    auth_enabled = _source_auth_enabled(src, caps)
    auth_priority = _source_auth_priority(src)
    return {
        "id": src.id,
        "type": src.type,
        "name": src.name,
        "domain_name": src.domain_name,
        "external_id": src.external_id,
        "protocol": src.protocol,
        "host": src.host,
        "port": src.port,
        "base_dn": src.base_dn,
        "bind_dn": src.bind_dn,
        "bind_password": None,
        "bind_password_ref": src.bind_password_ref,
        "auth_enabled": auth_enabled,
        "auth_priority": auth_priority,
        "capabilities": {
            "auth": auth_enabled,
            "import_groups": bool(caps.get("import_groups", True)),
            "snapshot_enabled": bool(caps.get("snapshot_enabled", False)),
            "auth_mode": caps.get("auth_mode", "ntlm"),
        },
        "is_active": bool(src.is_active),
    }


@router.get(
    "/resolve",
    summary="Resolve active identity source by domain (internal)",
)
def resolve_active_identity_source_by_domain(
    type: str = Query(default="ad", max_length=16),
    domain: str = Query(..., max_length=255),
    db: Session = Depends(get_db),
):
    domain_aliases = _domain_aliases(domain)
    if not domain_aliases:
        raise HTTPException(status_code=400, detail="domain is required")

    logger.info("identity source resolve by domain", extra={"type": type, "domain": domain})
    rows = _query_identity_sources(db, type)

    src = None
    for row in rows:
        if not _source_auth_enabled(row):
            continue
        row_aliases = _domain_aliases(row.domain_name)
        if row_aliases and (domain_aliases & row_aliases):
            src = row
            break

    if not src:
        logger.warning(
            "identity source not found by domain",
            extra={"type": type, "domain": domain},
        )
        raise HTTPException(status_code=404, detail="No active auth-enabled identity source for domain")

    logger.info(
        "identity source resolved by domain",
        extra={"id": src.id, "type": src.type, "domain": domain},
    )
    return _to_payload(src)


@router.get(
    "/{source_id}",
    summary="Get active identity source by id (internal, with secrets metadata)",
)
def get_identity_source_by_id(
    source_id: int,
    db: Session = Depends(get_db),
):
    logger.info("identity source resolve by id", extra={"id": int(source_id)})
    src = db.get(IdentitySource, int(source_id))
    if not src:
        raise HTTPException(status_code=404, detail="Identity source not found")
    if not _source_is_active(src) or not _source_auth_enabled(src):
        raise HTTPException(status_code=404, detail="Identity source not active for authentication")
    return _to_payload(src)


@router.get(
    "/active",
    summary="Get active identity source (internal, with secrets)",
)
def get_active_identity_source(
    type: str = Query(default="ad", max_length=16),
    db: Session = Depends(get_db),
):
    logger.info("identity source resolve", extra={"type": type})
    rows = _query_identity_sources(db, type)

    logger.debug("identity source candidates", extra={"count": len(rows)})

    src = next((row for row in rows if _source_auth_enabled(row)), None)

    if not src:
        logger.warning("identity source not found", extra={"type": type})
        raise HTTPException(status_code=404, detail="No active auth-enabled identity source")

    payload = _to_payload(src)
    logger.info("identity source resolved", extra={"id": src.id, "type": src.type})
    return payload
