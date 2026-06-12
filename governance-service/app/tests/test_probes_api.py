from __future__ import annotations

import asyncio
import pytest
from fastapi import HTTPException

from app.api import probes as api
from app.services import probe_service


def test_run_probe_returns_data_envelope(monkeypatch) -> None:
    async def _fake_submit_probe_run(payload: dict):
        _ = payload
        return {
            "job_id": "123",
            "status": "queued",
            "poll_url": "/api/probes/jobs/123",
        }

    monkeypatch.setattr(api, "submit_probe_run", _fake_submit_probe_run)

    payload = api.ProbeRunRequest(
        kind="identity-source",
        protocol="ldap",
        target={"host": "dc01.corp.local"},
        auth={"username": "svc"},
    )
    out = asyncio.run(api.run_probe(payload))

    assert out["data"]["job_id"] == "123"
    assert out["data"]["status"] == "queued"


def test_get_probe_job_returns_data_envelope(monkeypatch) -> None:
    async def _fake_fetch_probe_job(job_id: str):
        assert job_id == "123"
        return {
            "job_id": "123",
            "run_id": "123",
            "status": "succeeded",
            "result": {"success": True},
            "progress": {"step": "done"},
        }

    monkeypatch.setattr(api, "fetch_probe_job", _fake_fetch_probe_job)

    out = asyncio.run(api.get_probe_job("123"))
    assert out["data"]["job_id"] == "123"
    assert out["data"]["status"] == "succeeded"


def test_run_probe_input_validation_kept() -> None:
    with pytest.raises(Exception):
        _ = api.ProbeRunRequest(kind="", protocol="ldap", target={})


def test_probe_template_mapping_rejects_unknown_template() -> None:
    with pytest.raises(HTTPException) as exc:
        probe_service._job_type_for_template("unknown_template")

    assert exc.value.status_code == 500
    assert exc.value.detail["error_code"] == "PROBE_TEMPLATE_UNSUPPORTED"


def test_storage_root_probe_maps_to_smb_root_template() -> None:
    template, version = probe_service._pick_template("storage-root", "smb")

    assert template == "test_smb_root_access"
    assert version == "v1"
    assert probe_service._job_type_for_template(template) == "SMB_PROBE"


def test_storage_root_probe_enrichment_defaults_to_permissions_and_size(monkeypatch) -> None:
    async def _fake_dal_get(path: str, timeout: int = 5):
        assert path == "/api/internal/provisioning/storage-roots/8015/context"
        _ = timeout
        return {
            "storage_root_id": 8015,
            "storage_root_name": "FINANCE",
            "root_path": r"\\192.168.100.40\FINANCE",
            "storage_endpoint_id": 7011,
            "endpoint_port": 445,
            "endpoint_bind_dn": "svc-probe",
            "endpoint_bind_password_ref": "sm://endpoint/7011",
            "domain_name": "CORP",
        }

    monkeypatch.setattr(probe_service, "dal_get", _fake_dal_get)

    target, auth, options, context = asyncio.run(
        probe_service._enrich_storage_root_probe_payload(
            {
                "target": {"storage_root_id": 8015},
                "auth": {},
                "options": {},
                "context": {},
            }
        )
    )

    assert target["host"] == "192.168.100.40"
    assert target["share"] == "FINANCE"
    assert auth["username"] == "svc-probe"
    assert auth["secret_ref"] == "sm://endpoint/7011"
    assert options["discover_permissions"] is True
    assert options["discover_content_size"] is True
    assert context["storage_root_id"] == 8015
