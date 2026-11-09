"""Quotas: the payload sent to the worker, the express search states and the sizes in audit texts."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.services import folder_query, probe_service, quotas


def _ctx(**extra):
    return {"root_path": "\\\\10.0.0.5\\Angers\\Finance", "endpoint_bind_dn": "CORP\\svc", "endpoint_bind_password_ref": "sm://x/y",
            "endpoint_name": "FILER01.corp.local", "endpoint_type": "smb", "identity_source_host": "10.0.0.1", "domain_name": "corp.local", **extra}


def _enrich(monkeypatch, ctx, target):
    async def fake_call_route(_route, **_kwargs):
        return ctx

    monkeypatch.setattr(probe_service, "call_route", fake_call_route)
    return asyncio.run(probe_service._enrich_quota_payload({"kind": "folder", "protocol": "quota-apply", "target": {"storage_root_id": 7, **target}}))


def test_the_worker_gets_the_folder_its_server_name_and_a_domain_controller(monkeypatch) -> None:
    target, auth, options, context = _enrich(monkeypatch, _ctx(), {"operation": "set", "limit_bytes": 1024 ** 3, "warn_percent": 90})
    assert target["host"] == "10.0.0.5" and target["share"] == "Angers" and target["path"] == "Finance"
    assert target["server_name"] == "FILER01.corp.local" and target["kdc_host"] == "10.0.0.1"
    assert target["limit_bytes"] == 1024 ** 3 and target["warn_percent"] == 90 and target["soft"] is False
    assert auth == {"mode": "kerberos", "username": "CORP\\svc", "secret_ref": "sm://x/y", "domain": "corp.local"}
    assert context["storage_root_id"] == 7 and options["timeout_sec"] == 90


def test_a_dfs_folder_has_no_quota_of_its_own(monkeypatch) -> None:
    with pytest.raises(HTTPException) as refused:
        _enrich(monkeypatch, _ctx(endpoint_type="dfs"), {"operation": "read"})
    assert refused.value.detail["error_code"] == "QUOTA_DFS_UNSUPPORTED"


def test_quota_templates_are_mapped_to_their_job_types() -> None:
    assert probe_service._pick_template("folder", "quota-read") == ("folder_quota_read", "v1")
    assert probe_service._pick_template("folder", "quota-apply") == ("folder_quota_apply", "v1")
    assert probe_service._job_type_for_template("folder_quota_apply") == "FOLDER_QUOTA_APPLY"


@pytest.mark.parametrize("query,row,expected", [
    ("est:quota-plein", {"quota_limit_bytes": 100, "quota_used_percent": 91.0, "quota_warn_percent": 85}, True),
    ("est:quota-plein", {"quota_limit_bytes": 100, "quota_used_percent": 40.0, "quota_warn_percent": 85}, False),
    ("est:quota", {"quota_limit_bytes": 100}, True),
    ("est:sans-quota", {"quota_limit_bytes": None}, True),
    ("est:quota-demande", {"quota_pending_requests": 1}, True),
    ("est:mot-de-passe", {"password_files": 2, "sensitive_files": 3}, True),
    ("est:mot-de-passe", {"password_files": 0, "sensitive_files": 3}, False),
])
def test_express_search_states(query, row, expected) -> None:
    assert folder_query.matches(row, query) is expected
    assert folder_query.unknown_states(query) == []


def test_sizes_in_audit_texts() -> None:
    assert quotas.describe(10 * 1024 ** 3) == "10 GB"
    assert quotas.describe(1536 * 1024 ** 2) == "1.5 GB"
    assert quotas.describe(None) == "—"
