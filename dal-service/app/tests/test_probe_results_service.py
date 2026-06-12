from __future__ import annotations

from datetime import datetime, timezone

from app.models.storage_endpoint import StorageEndpoint
from app.models.storage_root import StorageRoot
from app.routers import provisioning_internal as provisioning_module
from app.routers.provisioning_internal import _extract_storage_endpoint_id_from_probe
from app.routers.storage_roots import StorageRootDiscoverySyncPayload
from app.repositories.storage_roots_views_repo import StorageRootsViewsRepo
from app.services.probe_results import ProbeResultService


class _NoopDB:
    pass


def test_initialize_storage_root_from_successful_endpoint_probe_sets_reachability_fields() -> None:
    probe_at = datetime(2026, 6, 5, 8, 30, tzinfo=timezone.utc)
    endpoint = StorageEndpoint(
        id=7011,
        name="FILER",
        endpoint_type="smb",
        protocol="smb",
        host="192.168.100.40",
        zone_id=1101,
        capabilities={},
        status="active",
        is_active=True,
        last_probe_status="success",
        last_probe_at=probe_at,
        last_probe_message="probe_ok",
    )

    data = {
        "storage_endpoint_id": 7011,
        "name": "FINANCE",
        "root_path": r"\\192.168.100.40\FINANCE",
        "status": "active",
    }

    initialized = ProbeResultService(_NoopDB()).initialize_storage_root_from_endpoint_probe(data, endpoint=endpoint)

    assert initialized["last_probe_status"] == "success"
    assert initialized["last_probe_at"] == probe_at
    assert initialized["last_probe_message"] == "endpoint_probe_ok"
    assert initialized["last_discovery_at"] == probe_at


def test_initialize_storage_root_preserves_explicit_root_probe_status() -> None:
    endpoint = StorageEndpoint(
        id=7011,
        name="FILER",
        endpoint_type="smb",
        protocol="smb",
        host="192.168.100.40",
        zone_id=1101,
        capabilities={},
        status="active",
        is_active=True,
        last_probe_status="success",
    )
    data = {
        "storage_endpoint_id": 7011,
        "name": "BROKEN",
        "root_path": r"\\192.168.100.40\BROKEN",
        "last_probe_status": "failed",
        "last_probe_message": "root_probe_failed",
    }

    initialized = ProbeResultService(_NoopDB()).initialize_storage_root_from_endpoint_probe(data, endpoint=endpoint)

    assert initialized is data
    assert initialized["last_probe_status"] == "failed"
    assert initialized["last_probe_message"] == "root_probe_failed"


def test_storage_root_discovery_sync_payload_defaults_to_complete_discovery() -> None:
    payload = StorageRootDiscoverySyncPayload(storage_endpoint_id=12, roots=[])

    assert payload.discovery_complete is True


def test_extract_storage_endpoint_id_from_smb_probe_prefers_result_details() -> None:
    endpoint_id = _extract_storage_endpoint_id_from_probe(
        job_payload_json={
            "payload": {
                "target": {"storage_endpoint_id": 10},
                "context": {"storage_endpoint_id": 11},
            }
        },
        result_json={"details": {"storage_endpoint_id": 12}},
    )

    assert endpoint_id == 12


def test_persist_storage_root_probe_failure_does_not_require_endpoint(monkeypatch) -> None:
    root = StorageRoot(
        id=8014,
        storage_endpoint_id=7011,
        name="Finance",
        root_path=r"\\files\finance",
        status="active",
    )

    class _DB:
        def get(self, model, ident):
            assert model is StorageRoot
            assert ident == 8014
            return root

    recorded = {}

    def _record(self, root_arg, **kwargs):
        recorded["root"] = root_arg
        recorded["kwargs"] = kwargs

    monkeypatch.setattr(provisioning_module.ProbeResultService, "record_storage_root_probe", _record)

    job = type(
        "Job",
        (),
        {
            "id": 54,
            "action": "test_smb_root_access",
            "payload_json": {"payload": {"target": {"storage_root_id": 8014}}},
        },
    )()

    provisioning_module._persist_storage_root_probe_result(
        _DB(),
        job_row=job,
        result_json={
            "success": False,
            "message": "SMB storage root read failed",
            "details": {"failure_code": "CAPSULE_PERMISSION_DENIED", "checks": []},
        },
        status_value="failed",
    )

    assert root.last_probe_status == "failed"
    assert root.last_probe_message == "SMB storage root read failed"
    assert recorded["root"] is root
    assert recorded["kwargs"]["metadata_json"]["failure_code"] == "CAPSULE_PERMISSION_DENIED"


def test_storage_root_effective_availability_distinguishes_endpoint_and_root_state() -> None:
    repo = StorageRootsViewsRepo(_NoopDB())

    assert repo._compute_effective_availability({"storage_endpoint_last_probe_status": "failed"}) == "blocked_by_endpoint"
    assert repo._compute_effective_availability({"needs_revalidation": True}) == "needs_revalidation"
    assert repo._compute_effective_availability(
        {"storage_endpoint_last_probe_status": "failed", "last_probe_status": "success"}
    ) == "reachable"
    assert repo._compute_effective_availability(
        {"storage_endpoint_last_probe_status": "success", "last_probe_status": "failed"}
    ) == "root_unreachable"
    assert repo._compute_effective_availability(
        {"storage_endpoint_last_probe_status": "success", "last_probe_status": None}
    ) == "needs_root_probe"
