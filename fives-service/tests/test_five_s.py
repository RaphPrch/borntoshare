"""5S scores, growth trend and forecast of the module (no database)."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.services import five_s, growth

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
    result = five_s.compute(rows)
    assert {"pillar": "order", "text": "Classer avec un tag", "folders": 3} in result["top_actions"]


def test_trend_needs_a_week_then_forecasts_the_full_quota() -> None:
    start = datetime(2026, 10, 1)
    assert growth.slope_per_day([(start, 100), (start + timedelta(days=2), 300)]) is None
    slope = growth.slope_per_day([(start + timedelta(days=d), 1000 + 100 * d) for d in range(0, 15)])
    assert round(slope) == 100
    forecast = growth.forecast(2000, 5000, slope)
    assert forecast["days_until_full"] == 30
    assert growth.forecast(2000, 5000, -5)["days_until_full"] is None
    assert growth.forecast(6000, 5000, 10)["days_until_full"] == 0


def test_duplicates_lower_the_sort_pillar_and_say_what_to_do() -> None:
    row = _row(cold_1y_bytes=0, cold_3y_bytes=0, dup_wasted_bytes=2 * GB, dup_groups=3, shared_dup_bytes=2 * GB, shared_dup_folders=2)
    result = five_s.score_folder(row, NOW - timedelta(days=10), NOW)
    assert result["pillars"]["sort"] == 70
    texts = [a["text"] for a in result["actions"] if a["pillar"] == "sort"]
    assert texts[0].startswith("Supprimer 2 Go de doublons") and texts[1].startswith("Dédoublonner 2 Go")
    assert five_s._family(texts[0]) == "Supprimer les doublons dans les dossiers"


