"""Reports of the core, the express search and the measure as its own job (no database)."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.services import folder_query, reports

NOW = datetime(2026, 11, 9, 12, 0)
GB = 1024 ** 3


def _row(**extra):
    base = {"storage_root_id": 1, "storage_root_name": "Lyon - Finance", "root_path": "\\\\filer\\Lyon\\Finance", "content_size_bytes": 10 * GB,
            "cold_1y_bytes": 4 * GB, "cold_3y_bytes": 2 * GB, "guardians_count": 2, "tags": [{"name": "Finance"}], "quota_limit_bytes": 20 * GB,
            "sensitive_files": 0, "password_files": 0, "key_files": 0, "junk_files": 0, "inheritance_broken": False,
            "open_alerts_error_count": 0, "last_probe_status": "success", "content_updated_at": (NOW - timedelta(days=2)).isoformat(),
            "pending_validation_count": 0, "quota_pending_requests": 0, "remediation_status": None, "zone_name": "Sud", "zone_id": 3,
            "storage_endpoint_name": "FILER01"}
    return {**base, **extra}


def test_reports_have_the_common_shape() -> None:
    rows = [_row(), _row(storage_root_id=2, storage_root_name="Lyon - RH", password_files=1, sensitive_files=1, guardians_count=1,
                       quota_used_percent=92.0, quota_warn_percent=85, quota_used_bytes=18 * GB)]
    for kind in ("storage", "governance"):
        report = reports.BUILDERS[kind](None, rows)
        assert report["kpis"] and all({"title", "columns", "rows"} <= set(section) for section in report["sections"])
    storage = reports.BUILDERS["storage"](None, rows)
    assert storage["kpis"][0]["value"] == 20 * GB
    assert "five_s" not in reports.KINDS  # served by the 5S module
    quotas = next(section for section in storage["sections"] if section["title"] == "Quotas")
    assert quotas["rows"][0]["status"] == "à surveiller"


def test_new_states_of_the_express_search() -> None:
    assert folder_query.matches({"key_files": 1}, "est:cle-ou-jeton")
    assert folder_query.matches({"remediation_status": "overdue"}, "est:correction")
    assert folder_query.matches({"content_size_bytes": 100, "cold_1y_bytes": 60}, "est:donnees-froides")
    assert not folder_query.matches({"content_size_bytes": 100, "cold_1y_bytes": 40}, "est:donnees-froides")
    assert folder_query.matches({"junk_files": 3}, "est:encombre")
    assert folder_query.unknown_states("est:cle-ou-jeton est:correction est:donnees-froides est:encombre") == []


def test_an_incremental_scan_keeps_what_it_did_not_read_again() -> None:
    from app.services import sensitivity

    previous = [
        {"path": "F\\a.ini", "category": "password", "line": 2},       # not read again: kept
        {"path": "F\\b.ini", "category": "password", "line": 1},       # read again, now clean: dropped
        {"path": "F\\gone.txt", "category": "password", "line": 3},    # deleted: dropped
        {"path": "F\\mdp.xlsx", "category": "credentials_file", "line": None},  # names are checked again every time
    ]
    scan = {"findings": [{"path": "F\\c.ps1", "category": "password", "line": 4}],
            "incremental": {"read_paths": ["F\\b.ini", "F\\c.ps1"], "gone_paths": ["F\\gone.txt"]}}
    merged = sensitivity._merge(previous, scan, same_rules=True)
    assert sorted(item["path"] for item in merged) == ["F\\a.ini", "F\\c.ps1"]
    assert [item["path"] for item in sensitivity._merge(previous, scan, same_rules=False)] == ["F\\c.ps1"]


def test_the_measure_is_its_own_job_and_a_dfs_folder_is_measured_through_smb(monkeypatch) -> None:
    import asyncio

    from app.services import probe_service

    assert probe_service._pick_template("folder", "measure") == ("folder_scan", "v1")
    assert probe_service._job_type_for_template("folder_scan") == "FOLDER_SCAN"
    ctx = {"root_path": "\\\\dfs01\\brest\\Finance", "endpoint_bind_dn": "CORP\\svc", "endpoint_bind_password_ref": "sm://x/y",
           "endpoint_name": "brest", "endpoint_type": "dfs", "identity_source_host": "10.0.0.1", "domain_name": "corp.local"}

    async def fake_call_route(_route, **_kwargs):
        return ctx

    monkeypatch.setattr(probe_service, "call_route", fake_call_route)
    target, auth, options, _context = asyncio.run(probe_service._enrich_quota_payload({"target": {"storage_root_id": 4}}, measure=True))
    assert target["server_name"] is None and "operation" not in target and options["timeout_sec"] == 3600 and auth["mode"] == "ntlm"


def test_doublons_and_tous_states() -> None:
    assert folder_query.matches({"dup_wasted_bytes": 1}, "est:doublons") and folder_query.matches({}, "est:tous")
