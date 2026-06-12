from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.models.identity_sources import IdentitySource
from app.models.storage_endpoint import StorageEndpoint
from app.routers import storage_endpoints as router
from app.services import storage_endpoint_provisioning as provisioning_service


class _FakeDB:
    def __init__(self, *, identity_source: IdentitySource | None = None):
        self.identity_source = identity_source

    def get(self, model, key):
        if model is IdentitySource and self.identity_source is not None and int(key) == int(self.identity_source.id):
            return self.identity_source
        return None


class _FakeZoneContextDB:
    def __init__(self):
        self.get_called = False

    def get(self, *_args, **_kwargs):
        self.get_called = True
        raise AssertionError("_resolve_zone_context must not use ORM db.get(Zone, ...) for legacy schemas")


def _source(*, source_id: int = 9, source_type: str = "ad", is_active: bool = True) -> IdentitySource:
    return IdentitySource(
        id=source_id,
        type=source_type,
        name="Corp AD",
        capabilities={},
        status="active",
        is_active=is_active,
    )


def _endpoint(*, identity_source_id: int | None) -> StorageEndpoint:
    return StorageEndpoint(
        id=1,
        zone_id=1,
        identity_source_id=identity_source_id,
        name="EP-01",
        endpoint_type="smb",
        protocol="smb",
        host="files.corp.local",
        capabilities={},
        status="active",
    )


def test_validate_identity_source_accepts_missing_value_for_smb() -> None:
    db = _FakeDB(identity_source=None)

    out = router._validate_identity_source_for_endpoint(
        db,
        identity_source_id=None,
        require_ad=True,
    )

    assert out is None


def test_validate_identity_source_rejects_inactive_source() -> None:
    db = _FakeDB(identity_source=_source(is_active=False))

    with pytest.raises(HTTPException) as exc:
        router._validate_identity_source_for_endpoint(
            db,
            identity_source_id=9,
            require_ad=True,
        )

    assert exc.value.status_code == 422
    assert (exc.value.detail or {}).get("error_code") == "ENDPOINT_IDENTITY_SOURCE_INACTIVE"


def test_validate_identity_source_rejects_non_ad_kind() -> None:
    db = _FakeDB(identity_source=_source(source_type="oidc", is_active=True))

    with pytest.raises(HTTPException) as exc:
        router._validate_identity_source_for_endpoint(
            db,
            identity_source_id=9,
            require_ad=True,
        )

    assert exc.value.status_code == 422
    assert (exc.value.detail or {}).get("error_code") == "ENDPOINT_IDENTITY_SOURCE_INVALID_KIND"


def test_validate_identity_source_accepts_active_ad_source() -> None:
    source = _source(source_type="ad", is_active=True)
    db = _FakeDB(identity_source=source)

    out = router._validate_identity_source_for_endpoint(
        db,
        identity_source_id=9,
        require_ad=True,
    )

    assert out is source


def test_build_endpoint_provisioning_payload_exposes_structured_identity_warnings(monkeypatch) -> None:
    source = _source(source_type="ad", is_active=True)
    source.bind_dn = ""
    source.bind_password_ref = ""
    source.host = ""
    source.base_dn = ""

    db = _FakeDB(identity_source=source)
    endpoint = _endpoint(identity_source_id=9)

    effective_row = {
        "storage_endpoint_id": 1,
        "zone_id": 1,
        "zone_name": "Z1",
        "endpoint_type": "smb",
        "protocol": "smb",
        "endpoint_sub_ou_dn": None,
        "endpoint_naming_template": None,
        "zone_naming_template": "{PREFIX}_{ROOTCODE}_{PERM}",
        "effective_ou_dn": None,
        "effective_identity_source_id": 9,
        "effective_identity_source_name": "Corp AD",
        "effective_identity_source_kind": "AD",
        "effective_identity_source_is_active": True,
        "effective_identity_source_bind_password_ref": "",
        "effective_identity_source_bind_dn": "",
        "effective_identity_source_host": "",
        "effective_identity_source_base_dn": "",
    }

    class _FakeRepo:
        def __init__(self, _db):
            self._db = _db

        def get_effective_provisioning_policy(self, _endpoint_id: int):
            return effective_row

    monkeypatch.setattr(provisioning_service, "StorageEndpointsViewsRepo", _FakeRepo)
    monkeypatch.setattr(provisioning_service, "load_zone_policy", lambda *_args, **_kwargs: {}, raising=False)
    monkeypatch.setattr(provisioning_service, "resolve_effective_policy", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        provisioning_service,
        "load_global_policy",
        lambda *_args, **_kwargs: {"template": "{PREFIX}_{ROOTCODE}_{PERM}", "group_prefix": "B2S"},
        raising=False,
    )

    payload = provisioning_service.build_storage_endpoint_provisioning_payload(db=db, endpoint=endpoint)
    warnings = payload.get("warnings") or []
    warning_codes = {str(item.get("code") or "") for item in warnings if isinstance(item, dict)}

    assert "IDENTITY_SOURCE_BIND_SECRET_MISSING" in warning_codes
    assert "IDENTITY_SOURCE_BIND_DN_MISSING" in warning_codes
    assert "IDENTITY_SOURCE_HOST_MISSING" in warning_codes
    assert "IDENTITY_SOURCE_BASE_DN_MISSING" in warning_codes


def test_build_endpoint_provisioning_payload_warns_when_identity_source_missing(monkeypatch) -> None:
    db = _FakeDB(identity_source=None)
    endpoint = _endpoint(identity_source_id=None)

    effective_row = {
        "storage_endpoint_id": 1,
        "zone_id": 1,
        "zone_name": "Z1",
        "endpoint_type": "smb",
        "protocol": "smb",
        "endpoint_sub_ou_dn": None,
        "endpoint_naming_template": None,
        "zone_naming_template": "{PREFIX}_{ROOTCODE}_{PERM}",
        "effective_ou_dn": None,
        "effective_identity_source_id": None,
        "effective_identity_source_name": None,
    }

    class _FakeRepo:
        def __init__(self, _db):
            self._db = _db

        def get_effective_provisioning_policy(self, _endpoint_id: int):
            return effective_row

    monkeypatch.setattr(provisioning_service, "StorageEndpointsViewsRepo", _FakeRepo)
    monkeypatch.setattr(provisioning_service, "load_zone_policy", lambda *_args, **_kwargs: {}, raising=False)
    monkeypatch.setattr(provisioning_service, "resolve_effective_policy", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        provisioning_service,
        "load_global_policy",
        lambda *_args, **_kwargs: {"template": "{PREFIX}_{ROOTCODE}_{PERM}", "group_prefix": "B2S"},
        raising=False,
    )

    payload = provisioning_service.build_storage_endpoint_provisioning_payload(db=db, endpoint=endpoint)
    warnings = payload.get("warnings") or []
    warning_codes = {str(item.get("code") or "") for item in warnings if isinstance(item, dict)}

    assert "IDENTITY_SOURCE_MISSING" in warning_codes


def test_build_endpoint_provisioning_payload_exposes_example_groups(monkeypatch) -> None:
    db = _FakeDB(identity_source=None)
    endpoint = _endpoint(identity_source_id=None)

    effective_row = {
        "storage_endpoint_id": 1,
        "zone_id": 1,
        "zone_name": "Z1",
        "endpoint_type": "smb",
        "protocol": "smb",
        "endpoint_sub_ou_dn": None,
        "endpoint_naming_template": None,
        "zone_naming_template": "{PREFIX}_{ROOTCODE}_{PERM}",
        "effective_ou_dn": "OU=Storage,DC=corp,DC=local",
        "effective_identity_source_id": None,
        "effective_identity_source_name": None,
    }

    class _FakeRepo:
        def __init__(self, _db):
            self._db = _db

        def get_effective_provisioning_policy(self, _endpoint_id: int):
            return effective_row

    monkeypatch.setattr(provisioning_service, "StorageEndpointsViewsRepo", _FakeRepo)
    monkeypatch.setattr(provisioning_service, "load_zone_policy", lambda *_args, **_kwargs: {}, raising=False)
    monkeypatch.setattr(provisioning_service, "resolve_effective_policy", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        provisioning_service,
        "load_global_policy",
        lambda *_args, **_kwargs: {
            "template": "{PREFIX}_{ROOTCODE}_{PERM}",
            "group_prefix": "B2S",
            "replace_map_json": '{"\\\\":"_","/":"_"," ":"_","-":"_"}',
            "rootcode_strategy": "BASENAME",
            "normalize_uppercase": True,
            "max_sam_length": 64,
        },
        raising=False,
    )

    payload = provisioning_service.build_storage_endpoint_provisioning_payload(db=db, endpoint=endpoint)
    example = payload.get("example_groups") or {}
    naming_policy = payload.get("effective_naming_policy") or {}

    assert str(example.get("based_on_root_code") or "") == "FINANCE_RW"
    assert str(example.get("read") or "") == "B2S_FINANCE_RW_RX"
    assert str(example.get("write") or "") == "B2S_FINANCE_RW"
    assert str(naming_policy.get("group_prefix") or "") == "B2S"
    assert str(naming_policy.get("template") or "") == "{PREFIX}_{ROOTCODE}_{PERM}"
    assert str(naming_policy.get("rootcode_strategy") or "") == "BASENAME"


def test_normalize_update_accepts_canonical_inherit_payload() -> None:
    out = provisioning_service.normalize_storage_endpoint_provisioning_update(
        {
            "policy_mode": "inherit",
            "endpoint_values": {
                "ou_dn": None,
                "naming_template": None,
            },
        }
    )

    assert out["policy_mode"] == "inherit"
    assert out["endpoint_override_enabled"] is False
    assert out["endpoint_values"]["ou_dn"] is None
    assert out["endpoint_values"]["naming_template"] is None


def test_normalize_update_rejects_empty_override_payload() -> None:
    with pytest.raises(HTTPException) as exc:
        provisioning_service.normalize_storage_endpoint_provisioning_update(
            {
                "policy_mode": "override",
                "endpoint_values": {"ou_dn": "", "naming_template": ""},
            }
        )

    assert exc.value.status_code == 422
    assert (exc.value.detail or {}).get("error_code") == "ENDPOINT_OVERRIDE_VALUES_REQUIRED"


def test_normalize_update_rejects_missing_policy_mode() -> None:
    with pytest.raises(HTTPException) as exc:
        provisioning_service.normalize_storage_endpoint_provisioning_update(
            {
                "endpoint_values": {
                    "ou_dn": None,
                    "naming_template": "{PREFIX}_{ROOTCODE}_{PERM}",
                },
            }
        )

    assert exc.value.status_code == 422
    assert (exc.value.detail or {}).get("error_code") == "INVALID_POLICY_MODE"


def test_resolve_zone_context_reads_zone_name_via_read_model(monkeypatch) -> None:
    db = _FakeZoneContextDB()

    class _FakeRepo:
        def __init__(self, _db):
            self._db = _db

        def get_overview(self, endpoint_id: int):
            assert endpoint_id == 44
            return {"zone_id": 12, "zone_name": "Zone Twelve"}

    monkeypatch.setattr(router, "StorageEndpointsViewsRepo", _FakeRepo)

    out = router._resolve_zone_context(db, endpoint_id_value=44, zone_id_value=12)

    assert out == {"id": 12, "name": "Zone Twelve"}
    assert db.get_called is False


def test_resolve_zone_context_falls_back_to_zone_id_when_read_model_missing(monkeypatch) -> None:
    db = _FakeZoneContextDB()

    class _FakeRepo:
        def __init__(self, _db):
            self._db = _db

        def get_overview(self, _endpoint_id: int):
            return None

    monkeypatch.setattr(router, "StorageEndpointsViewsRepo", _FakeRepo)

    out = router._resolve_zone_context(db, endpoint_id_value=44, zone_id_value=91)

    assert out == {"id": 91, "name": "Zone #91"}
    assert db.get_called is False


def test_resolve_zone_context_falls_back_to_zone_id_when_zone_name_empty(monkeypatch) -> None:
    db = _FakeZoneContextDB()

    class _FakeRepo:
        def __init__(self, _db):
            self._db = _db

        def get_overview(self, _endpoint_id: int):
            return {"zone_id": 99, "zone_name": ""}

    monkeypatch.setattr(router, "StorageEndpointsViewsRepo", _FakeRepo)

    out = router._resolve_zone_context(db, endpoint_id_value=44, zone_id_value=91)

    assert out == {"id": 99, "name": "Zone #99"}
    assert db.get_called is False


def test_resolve_zone_context_returns_null_payload_when_zone_id_missing(monkeypatch) -> None:
    db = _FakeZoneContextDB()

    class _FakeRepo:
        def __init__(self, _db):
            self._db = _db

        def get_overview(self, _endpoint_id: int):
            return None

    monkeypatch.setattr(router, "StorageEndpointsViewsRepo", _FakeRepo)

    out = router._resolve_zone_context(db, endpoint_id_value=None, zone_id_value=None)

    assert out == {"id": None, "name": None}


class _Rows:
    def __init__(self, rows: list[dict] | None = None):
        self._rows = list(rows or [])

    def mappings(self):  # noqa: ANN201
        return self

    def all(self):  # noqa: ANN201
        return list(self._rows)


class _FakeCascadeDB:
    def __init__(self):
        self.updated: list[dict] = []

    def execute(self, statement, params=None):  # noqa: ANN001, ANN201
        sql = str(statement).lower()
        payload = dict(params or {})
        if "from storage_roots" in sql and "where storage_endpoint_id = :endpoint_id" in sql:
            return _Rows(
                [
                    {"id": 8101, "name": "FIN-Shared", "root_path": "/shares/fin/shared", "last_probe_status": "success"},
                    {"id": 8102, "name": "FIN-Archive", "root_path": "/shares/fin/archive", "last_probe_status": "running"},
                ]
            )
        if sql.strip().startswith("update storage_roots"):
            self.updated.append(payload)
            return _Rows([])
        return _Rows([])


def test_cascade_endpoint_probe_failure_to_roots_updates_all_associated_roots() -> None:
    db = _FakeCascadeDB()
    probe_at = datetime(2026, 4, 19, 10, 0, 0, tzinfo=timezone.utc)

    impacted = router._cascade_endpoint_probe_failure_to_roots(
        db,
        endpoint_id=7001,
        probe_at=probe_at,
        probe_message="Storage endpoint probe failed: timeout",
    )

    assert len(impacted) == 2
    assert {int(row["id"]) for row in impacted} == {8101, 8102}
    assert len(db.updated) == 2
    assert all(str(item.get("probe_message") or "").startswith("Storage endpoint probe failed") for item in db.updated)


class _FakeUpdateDB:
    def __init__(self, endpoint: StorageEndpoint):
        self.endpoint = endpoint

    def get(self, model, key):  # noqa: ANN001, ANN201
        if model is StorageEndpoint and int(key) == int(getattr(self.endpoint, "id", 0) or 0):
            return self.endpoint
        return None

    def commit(self):
        return None

    def rollback(self):
        return None


def test_update_endpoint_probe_failure_logs_root_unavailable_activity(monkeypatch) -> None:
    endpoint = StorageEndpoint(
        id=7001,
        zone_id=1101,
        identity_source_id=2,
        name="SMB-PAR-01",
        endpoint_type="smb",
        protocol="smb",
        host="files-par-01.corp.local",
        capabilities={},
        status="active",
        is_active=True,
    )
    db = _FakeUpdateDB(endpoint)
    activity_calls: list[dict] = []

    monkeypatch.setattr(router, "_resolve_zone_context", lambda *_a, **_k: {"id": 1101, "name": "Zone PAR-1"})

    class _FakeProbeResultService:
        def __init__(self, _db):
            pass

        def record_storage_endpoint_probe(self, *_args, **_kwargs):  # noqa: ANN201
            return [
                {"id": 8001, "name": "FIN-Shared", "root_path": "/shares/fin/shared", "previous_probe_status": "success"}
            ]

    monkeypatch.setattr(router, "ProbeResultService", _FakeProbeResultService)
    monkeypatch.setattr(router, "log_activity", lambda *_a, **kwargs: activity_calls.append(dict(kwargs)))

    payload = router.StorageEndpointUpdate(
        last_probe_status="failed",
        last_probe_at="2026-04-19T10:31:00Z",
        last_probe_message="probe timeout",
    )

    out = router.update_endpoint(
        endpoint_id=7001,
        payload=payload,
        request=SimpleNamespace(
            headers={
                "x-request-id": "rid-1",
                "x-identity-id": "42",
                "x-actor-display": "Admin Local",
                "x-roles": "platform_admin",
            }
        ),
        db=db,
    )

    assert int((out.get("data") or {}).get("id") or 0) == 7001
    assert len(activity_calls) >= 2
    endpoint_activity = next((c for c in activity_calls if c.get("action") == "storage_endpoint.updated"), None)
    root_activity = next((c for c in activity_calls if c.get("action") == "storage_root.unavailable_from_endpoint_probe"), None)
    assert endpoint_activity is not None
    assert root_activity is not None
    assert root_activity.get("target_type") == "storage_root"
    assert int(root_activity.get("target_id") or 0) == 8001
