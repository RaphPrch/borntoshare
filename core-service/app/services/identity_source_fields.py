"""Read helpers for identity source rows (tolerant of optional columns)."""
from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.data.models.identity_sources import IdentitySource


def identity_source_columns(db: Session) -> set[str]:
    try:
        inspector = inspect(db.get_bind())
        return {col["name"] for col in inspector.get_columns(IdentitySource.__tablename__)}
    except Exception:
        return set()


def source_capabilities(src: IdentitySource) -> dict[str, object]:
    raw = src.__dict__.get("capabilities")
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def source_auth_enabled(src: IdentitySource, caps: dict[str, object] | None = None) -> bool:
    if "auth_enabled" in src.__dict__:
        return bool(src.__dict__.get("auth_enabled"))
    effective_caps = caps if isinstance(caps, dict) else source_capabilities(src)
    return bool(effective_caps.get("auth", False))


def source_auth_priority(src: IdentitySource) -> int:
    if "auth_priority" in src.__dict__:
        raw = src.__dict__.get("auth_priority")
        try:
            return int(raw or 100)
        except Exception:
            return 100
    return 100
