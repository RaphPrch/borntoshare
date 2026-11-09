"""The module: its reports, and nothing without the license."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import core_client
from app.services import reports


def _row(i, **extra):
    return {"storage_root_id": i, "storage_root_name": f"F{i}", "root_path": f"\\\\filer\\S\\F{i}", "content_size_bytes": 1000, "cold_1y_bytes": 600,
            "cold_3y_bytes": 300, "junk_files": 2, "junk_bytes": 10, "dup_wasted_bytes": 100, "dup_groups": 1, "shared_dup_bytes": 50,
            "shared_dup_folders": 1, "growth_30d_bytes": 20, "zone_name": "Z", "guardians_count": 2, "tags": [], "last_probe_status": "success", **extra}


def test_both_reports_have_the_common_shape() -> None:
    rows = [_row(1), _row(2)]
    for kind in reports.KINDS:
        report = reports.build(kind, rows, "Tous", {"bytes": 50, "files": 1})
        assert report["key"] == kind and report["kpis"]
        assert all({"title", "columns", "rows"} <= set(section) for section in report["sections"])
    hygiene = reports.build("fives-hygiene", rows, "Tous", {"bytes": 50, "files": 1})
    assert hygiene["kpis"][1]["value"] == 250  # 2 × 100 inside + 50 between


def test_nothing_without_the_license(monkeypatch) -> None:
    monkeypatch.setattr(core_client, "license_state", lambda: {"licensed": True, "enabled": False})
    with pytest.raises(HTTPException) as refused:
        core_client.require_license()
    assert refused.value.status_code == 403 and refused.value.detail["error_code"] == "FEATURE_DISABLED"
    monkeypatch.setattr(core_client, "license_state", lambda: {"licensed": True, "enabled": True})
    assert core_client.require_license()["enabled"] is True


def test_the_identity_is_trusted_only_with_the_internal_token() -> None:
    from starlette.requests import Request

    from app.auth import actor

    def request(headers):
        return Request({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers.items()]})

    with pytest.raises(HTTPException):
        actor(request({"x-roles": "platform_admin"}))
    who = actor(request({"x-internal-token": "test-internal-token", "x-roles": "platform_admin", "x-identity-id": "7"}))
    assert who.is_admin and who.identity_id == 7
