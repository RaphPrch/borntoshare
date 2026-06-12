from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import create_engine
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

# 🔴 OBLIGATOIRE : charge TOUS les modèles avant toute requête ORM
import app.models  # noqa: F401

# ✅ Base vient des modèles, PAS d'ici
from app.models.base import Base
settings = get_settings()


_SCHEMA_GUARD_CHECKED = False


_REQUIRED_TABLE_COLUMNS: dict[str, set[str]] = {
    "storage_endpoints": {
        "id",
        "zone_id",
        "name",
        "naming_template",
    },
    "identity_sources": {
        "id",
        "default_group_ou_dn",
        "base_dn",
    },
    "local_credentials": {
        "id",
        "identity_id",
        "password_hash",
    },
    "storage_root_tags": {
        "id",
        "storage_root_id",
        "tag_id",
    },
    "storage_roots": {
        "id",
        "storage_endpoint_id",
        "parent_storage_root_id",
        "root_path",
        "normalized_root_path",
        "inherit_owners",
        "inherit_tags",
        "inherit_access_profiles",
        "discovered_tree_json",
        "needs_revalidation",
        "revalidation_reason",
    },
    "governance_alerts": {
        "id",
        "alert_key",
        "scope_type",
        "scope_id",
        "alert_type",
        "severity",
        "status",
        "title",
        "storage_root_id",
        "last_seen_at",
    },
    "governance_health_events": {
        "id",
        "entity_type",
        "entity_id",
        "check_type",
        "status",
        "severity",
        "checked_at",
    },
    "zone_access_profiles": {
        "zone_id",
        "access_profile_id",
        "updated_at",
    },
}


_REQUIRED_VIEWS: set[str] = {
    "v_storage_endpoint_provisioning_effective",
    "v_storage_root_provisioning_effective",
    "v_zone_provisioning_policy_effective",
    "v_storage_roots_context",
    "v_access_requests",
    "v_access_request_timeline",
    "v_access_request_provisioning",
    "v_identity_source_latest_snapshot",
    "v_storage_root_access_profile_users",
}


def _assert_table_has_columns(*, table: str, available: Iterable[str], required: Iterable[str]) -> None:
    available_set = {str(c) for c in available}
    required_set = {str(c) for c in required}
    missing = sorted(required_set - available_set)
    if missing:
        missing_cols = ", ".join(missing)
        raise RuntimeError(
            "DB schema contract violation: "
            f"table '{table}' is missing required columns: {missing_cols}. "
            "Apply Wizard SQL schema pack including storage_endpoints naming_template alignment."
        )


def assert_runtime_schema_contract(bind=None) -> None:
    if not settings.DB_SCHEMA_GUARD_ENABLED:
        return

    inspector = inspect(bind or engine)

    for table, required_cols in _REQUIRED_TABLE_COLUMNS.items():
        try:
            columns = inspector.get_columns(table)
        except Exception as exc:
            raise RuntimeError(
                "DB schema contract violation: "
                f"required table '{table}' is not introspectable."
            ) from exc

        available_cols = [str(col.get("name") or "") for col in columns]
        _assert_table_has_columns(
            table=table,
            available=available_cols,
            required=required_cols,
        )

    try:
        available_views = {str(name) for name in inspector.get_view_names()}
    except Exception as exc:
        raise RuntimeError(
            "DB schema contract violation: required SQL views are not introspectable."
        ) from exc

    missing_views = sorted(v for v in _REQUIRED_VIEWS if v not in available_views)
    if missing_views:
        raise RuntimeError(
            "DB schema contract violation: missing required SQL views: "
            + ", ".join(missing_views)
            + ". Apply Wizard SQL views pack."
        )


def ensure_schema_contract_checked(bind=None) -> None:
    global _SCHEMA_GUARD_CHECKED
    if _SCHEMA_GUARD_CHECKED:
        return
    assert_runtime_schema_contract(bind=bind)
    _SCHEMA_GUARD_CHECKED = True


# ============================================================
# Engine
# ============================================================

engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ============================================================
# Dependency
# ============================================================

def get_db():
    db = SessionLocal()
    try:
        ensure_schema_contract_checked(bind=db.get_bind())
        yield db
    finally:
        db.close()
