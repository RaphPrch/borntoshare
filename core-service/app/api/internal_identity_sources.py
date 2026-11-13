from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.data.repositories import lookups_repo
from app.core.db import get_db
from app.core.logging import get_logger
from app.core.internal_auth import require_internal
from app.data.models.identity_sources import IdentitySource
from app.services.identity_source_accounts import load_accounts
from app.services.identity_source_fields import (
    identity_source_columns,
    source_auth_enabled,
    source_auth_priority,
    source_capabilities,
)

router = APIRouter(
    prefix="/internal/identity-sources",
    tags=["internal-identity-sources"],
    dependencies=[require_internal({"jobs:read"})],
)
logger = get_logger("core-identity-sources")


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


def _to_payload(src: IdentitySource, db: Session | None = None) -> dict:
    caps = source_capabilities(src)
    auth_enabled = source_auth_enabled(src, caps)
    auth_priority = source_auth_priority(src)
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
        "directory_flavor": src.directory_flavor,
        "tls_verify": bool(src.tls_verify),
        "tls_ca_pem": src.tls_ca_pem,
        "tls_server_name": src.tls_server_name,
        "user_filter": src.user_filter,
        "auth_enabled": auth_enabled,
        "auth_priority": auth_priority,
        "capabilities": {
            "auth": auth_enabled,
            "import_groups": bool(caps.get("import_groups", True)),
            "snapshot_enabled": bool(caps.get("snapshot_enabled", False)),
            "provisioning": bool(getattr(src, "write_enabled", False)),
            "auth_mode": caps.get("auth_mode", "ntlm"),
        },
        # Dedicated accounts by capability (auth-service uses "auth"), with their secret references
        "service_accounts": load_accounts(db, int(src.id)) if db is not None else {},
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
    rows = lookups_repo.auth_identity_sources(db, type)

    src = None
    for row in rows:
        if not source_auth_enabled(row):
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
    return _to_payload(src, db)


@router.get(
    "/{source_id:int}",  # a number only: « /active » and « /resolve » are not ids
    summary="Get active identity source by id (internal, with secrets metadata)",
)
def get_identity_source_by_id(
    source_id: int,
    db: Session = Depends(get_db),
):
    logger.info("identity source resolve by id", extra={"id": int(source_id)})
    src = lookups_repo.identity_source(db, int(source_id))
    if not src:
        raise HTTPException(status_code=404, detail="Identity source not found")
    if not lookups_repo._source_is_active(src) or not source_auth_enabled(src):
        raise HTTPException(status_code=404, detail="Identity source not active for authentication")
    return _to_payload(src, db)


@router.get(
    "/active",
    summary="Get active identity source (internal, with secrets)",
)
def get_active_identity_source(
    type: str = Query(default="ad", max_length=16),
    db: Session = Depends(get_db),
):
    logger.info("identity source resolve", extra={"type": type})
    rows = lookups_repo.auth_identity_sources(db, type)

    logger.debug("identity source candidates", extra={"count": len(rows)})

    src = next((row for row in rows if source_auth_enabled(row)), None)

    if not src:
        logger.warning("identity source not found", extra={"type": type})
        raise HTTPException(status_code=404, detail="No active auth-enabled identity source")

    payload = _to_payload(src, db)
    logger.info("identity source resolved", extra={"id": src.id, "type": src.type})
    return payload
