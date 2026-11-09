"""5S scores, growth trend and forecast, and the reports built from folder rows (no database)."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.services import content_history, five_s, folder_query, reports

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


def test_a_well_kept_folder_scores_high_and_says_what_is_left() -> None:
    result = five_s.score_folder(_row(), NOW - timedelta(days=10), NOW)
    assert result["pillars"] == {"sort": 70, "order": 100, "shine": 100, "standard": 100, "sustain": 100}
    assert result["score"] == 94
    assert [a["pillar"] for a in result["actions"]] == ["sort"]


def test_a_neglected_folder_gets_its_actions() -> None:
    row = _row(guardians_count=0, tags=[], quota_limit_bytes=None, password_files=2, sensitive_files=2, junk_files=40, junk_bytes=GB,
               inheritance_broken=True, last_probe_status="failed", content_updated_at=None, remediation_status="overdue")
    result = five_s.score_folder(row, None, NOW)
    assert result["pillars"]["order"] == 0 and result["pillars"]["shine"] == 30 and result["pillars"]["standard"] == 30
    assert result["pillars"]["sustain"] == 25
    texts = " | ".join(a["text"] for a in result["actions"])
    assert "Nommer des gardiens" in texts and "en retard" in texts and "Supprimer 40 fichier(s) parasite(s)" in texts


def test_pillars_without_data_give_no_score() -> None:
    result = five_s.score_folder(_row(content_size_bytes=None, cold_1y_bytes=None, sensitive_files=None, junk_files=None), None, NOW)
    assert result["pillars"]["sort"] is None and result["pillars"]["shine"] is None


def test_top_actions_group_the_same_action_across_folders() -> None:
    rows = [_row(storage_root_id=i, tags=[]) for i in range(1, 4)]
    result = five_s.compute(rows, {})
    assert {"pillar": "order", "text": "Classer avec un tag", "folders": 3} in result["top_actions"]


def test_trend_needs_a_week_then_forecasts_the_full_quota() -> None:
    start = datetime(2026, 10, 1)
    assert content_history.slope_per_day([(start, 100), (start + timedelta(days=2), 300)]) is None
    slope = content_history.slope_per_day([(start + timedelta(days=d), 1000 + 100 * d) for d in range(0, 15)])
    assert round(slope) == 100
    forecast = content_history.forecast(2000, 5000, slope)
    assert forecast["days_until_full"] == 30
    assert content_history.forecast(2000, 5000, -5)["days_until_full"] is None
    assert content_history.forecast(6000, 5000, 10)["days_until_full"] == 0


def test_reports_have_the_common_shape() -> None:
    rows = [_row(), _row(storage_root_id=2, storage_root_name="Lyon - RH", password_files=1, sensitive_files=1, guardians_count=1,
                       quota_used_percent=92.0, quota_warn_percent=85, quota_used_bytes=18 * GB)]
    for kind in ("storage", "governance"):
        report = reports.BUILDERS[kind](None, rows)
        assert report["kpis"] and all({"title", "columns", "rows"} <= set(section) for section in report["sections"])
    storage = reports.BUILDERS["storage"](None, rows)
    assert storage["kpis"][0]["value"] == 20 * GB
    quotas = next(section for section in storage["sections"] if section["title"] == "Quotas")
    assert quotas["rows"][0]["status"] == "à surveiller"


def test_new_states_of_the_express_search() -> None:
    assert folder_query.matches({"key_files": 1}, "est:cle-ou-jeton")
    assert folder_query.matches({"remediation_status": "overdue"}, "est:correction")
    assert folder_query.matches({"content_size_bytes": 100, "cold_1y_bytes": 60}, "est:donnees-froides")
    assert not folder_query.matches({"content_size_bytes": 100, "cold_1y_bytes": 40}, "est:donnees-froides")
    assert folder_query.matches({"junk_files": 3}, "est:encombre")
    assert folder_query.unknown_states("est:cle-ou-jeton est:correction est:donnees-froides est:encombre") == []
