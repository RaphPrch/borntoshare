from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def _extract_function_source(module_text: str, func_name: str) -> str:
    pattern = re.compile(
        rf"^def\s+{re.escape(func_name)}\s*\(.*?(?=^@router\.|^def\s+|\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(module_text)
    assert match is not None, f"function not found: {func_name}"
    return match.group(0)


def test_ldap_client_import_is_confined_to_snapshot_service() -> None:
    app_dir = ROOT / "app"
    allowed = {"app/services/directory_snapshot_service.py"}
    offenders: list[str] = []

    for path in app_dir.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("app/tests/"):
            continue
        if rel in {"app/services/ldap_client.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if "from app.services.ldap_client import" in text and rel not in allowed:
            offenders.append(rel)

    assert offenders == []


def test_identity_list_router_has_no_direct_ldap_import() -> None:
    src = _read("app/routers/identity_list.py")
    assert "from app.services.ldap_client import" not in src


def test_directory_snapshot_service_uses_only_open_connection_from_ldap_client() -> None:
    src = _read("app/services/directory_snapshot_service.py")
    assert "from app.services.ldap_client import _open_connection" in src
    forbidden_tokens = [
        "ensure_group_member(",
        "ensure_group_exists(",
        "remove_group_member(",
        "search_principals(",
        "discover_group_users_recursive(",
    ]
    for token in forbidden_tokens:
        assert token not in src


def test_zones_get_routes_do_not_contain_write_sql() -> None:
    src = _read("app/routers/zones.py")
    get_functions = [
        "list_zones",
        "get_zone_overview",
        "get_zone_console",
        "get_zone_provisioning_policy",
        "get_zone_provisioning_drift",
        "list_zone_access_profiles",
        "get_zone",
    ]
    forbidden_markers = [
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "db.commit(",
    ]

    for func_name in get_functions:
        body = _extract_function_source(src, func_name).upper()
        for marker in forbidden_markers:
            assert marker not in body, f"{func_name} contains write marker: {marker}"


def test_storage_endpoints_schema_declares_naming_template_column() -> None:
    schema = _read("../wizard-ui/backend/app/sql/schema/030_storage.sql")
    normalized = schema.lower()
    assert "create table if not exists storage_endpoints" in normalized
    assert "naming_template varchar(190) null" in normalized
    assert "endpoint_url" not in normalized
    assert "ip_address" not in normalized
    assert "hostname" not in normalized


def test_storage_roots_schema_declares_hierarchy_columns() -> None:
    schema = _read("../wizard-ui/backend/app/sql/schema/030_storage.sql")
    normalized = schema.lower()
    storage_roots = normalized.split("create table if not exists storage_roots", 1)[1].split(");", 1)[0]
    assert "parent_storage_root_id bigint unsigned null" in storage_roots
    assert "normalized_root_path varchar(512) null" in storage_roots
    assert "inherit_owners tinyint(1) not null default 0" in storage_roots
    assert "inherit_tags tinyint(1) not null default 0" in storage_roots
    assert "inherit_access_profiles tinyint(1) not null default 0" in storage_roots
    assert "fk_storage_roots_parent_storage_root_id" in storage_roots
    assert "references storage_roots(id) on delete restrict" in storage_roots


def test_identity_sources_schema_has_no_legacy_kind_or_secret_ref_columns() -> None:
    schema = _read("../wizard-ui/backend/app/sql/schema/020_identity.sql")
    normalized = schema.lower()
    assert "create table if not exists identity_sources" in normalized
    assert " kind varchar(" not in normalized
    assert " secret_ref varchar(" not in normalized


def test_zones_schema_keeps_provisioning_ou_out_of_zone_table() -> None:
    schema = _read("../wizard-ui/backend/app/sql/schema/010_core.sql")
    normalized = schema.lower()
    zones_table = normalized.split("create table if not exists zones", 1)[1].split(");", 1)[0]
    assert "default_group_ou_dn" not in zones_table


def test_local_credentials_schema_enforces_one_row_per_identity() -> None:
    schema = _read("../wizard-ui/backend/app/sql/schema/020_identity.sql")
    normalized = schema.lower()
    local_credentials = normalized.split("create table if not exists local_credentials", 1)[1].split(");", 1)[0]
    assert "id bigint unsigned primary key auto_increment" in local_credentials
    assert "uq_local_credentials_identity_id unique (identity_id)" in local_credentials


def test_dal_runtime_schema_guard_requires_storage_endpoint_naming_template() -> None:
    db_src = _read("app/core/db.py")
    normalized = db_src.lower()
    assert "_required_table_columns" in normalized
    assert "storage_endpoints" in normalized
    assert "naming_template" in normalized


def test_dal_runtime_schema_guard_requires_access_requests_read_model_views() -> None:
    db_src = _read("app/core/db.py")
    normalized = db_src.lower()
    assert "_required_views" in normalized
    assert "v_access_requests" in normalized
    assert "v_access_request_timeline" in normalized
    assert "v_access_request_provisioning" in normalized


def test_identity_sources_snapshot_read_model_is_repo_backed() -> None:
    src = _read("app/routers/identity_sources.py")
    normalized = src.lower()
    assert "identitysourcesviewsrepo" in normalized
    assert "from directory_snapshots" not in normalized


def test_directory_snapshots_schema_keeps_source_version_uniqueness_contract() -> None:
    schema = _read("../wizard-ui/backend/app/sql/schema/080_snapshots.sql")
    normalized = schema.lower()
    assert "uq_directory_snapshots_source_version" in normalized
    assert "unique (identity_source_id, version)" in normalized
    assert "idx_directory_snapshots_source_status_created" in normalized


def test_directory_snapshots_repo_create_run_has_integrity_retry_loop() -> None:
    src = _read("app/repositories/directory_snapshots_repo.py")
    normalized = src.lower()
    assert "max_attempts" in normalized
    assert "except integrityerror" in normalized
    assert "continue" in normalized
