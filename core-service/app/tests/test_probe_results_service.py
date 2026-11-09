from __future__ import annotations


from app.data.models.storage_root import StorageRoot
from app.api import provisioning_internal as provisioning_module
from app.api.provisioning_internal import _extract_storage_endpoint_id_from_probe
from app.api.storage_roots import StorageRootDiscoverySyncPayload
from app.data.repositories.storage_roots_views_repo import StorageRootsViewsRepo


class _NoopDB:
    pass


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


def test_a_test_that_reads_the_acl_keeps_the_last_measure(monkeypatch) -> None:
    """The test no longer measures: reading the ACL again must not wipe the content of the last measure."""
    measured = {"content_size_bytes": 1234, "content_updated_at": "2026-11-09T19:00:00+00:00", "content_stats": {"files": 3}, "content_scan_job_id": 9}
    root = StorageRoot(id=8015, storage_endpoint_id=0, name="Finance", root_path=r"\\files\finance", status="active",
                       discovered_permissions_json={"permissions": [], **measured})

    class _DB:
        def get(self, model, ident):
            return root

    monkeypatch.setattr(provisioning_module.ProbeResultService, "record_storage_root_probe", lambda self, root_arg, **kwargs: None)
    job = type("Job", (), {"id": 55, "action": "test_smb_root_access", "payload_json": {"payload": {"target": {"storage_root_id": 8015}}}})()
    provisioning_module._persist_storage_root_probe_result(
        _DB(), job_row=job, status_value="success",
        result_json={"success": True, "message": "ok", "details": {"checks": [{"name": "root_acl", "ok": True}],
                                                                   "permissions": [{"principal": "CORP\\g", "rights": "READ"}]}},
    )
    assert {key: root.discovered_permissions_json.get(key) for key in measured} == measured
    assert root.discovered_permissions_json["permissions_count"] == 1
