"""Access review campaigns and the monthly report: what can be tested without a database."""
from __future__ import annotations

from datetime import datetime

from app.api.governance.access_reviews import _manual_reason
from app.services import monthly_report


def test_an_access_outside_borntoshare_says_which_group_to_leave() -> None:
    item = {"via": [{"kind": "outside", "group": "GG_ANCIEN"}, {"kind": "ad_only", "group": "GG_FINANCE_RW"}, {"kind": "request", "code": "AR-1"}]}
    assert _manual_reason(item) == "Accès hors BornToShare : retirer la personne de GG_ANCIEN, GG_FINANCE_RW"
    assert _manual_reason({"via": []}).startswith("Accès hors BornToShare")


def test_the_report_covers_the_month_before() -> None:
    since, until, label = monthly_report.previous_month(datetime(2026, 1, 1, 6, 0))
    assert (since, until, label) == (datetime(2025, 12, 1), datetime(2026, 1, 1), "décembre 2025")


def test_the_report_reads_as_sections_with_or_without_the_5s_module() -> None:
    data = {"governance": {"requests": 4, "approved": 3, "rejected": 1, "revoked": 2, "active": 40, "alerts_open": 5, "alerts_critical": 1, "folders": 12},
            "reviews": {"open": 1, "decided": 30, "removed": 4, "waiting": 6}, "fives": None}
    sections = monthly_report.lines(data)
    assert [title for title, _rows in sections] == ["Accès", "Revue des accès", "Alertes"]
    assert ("Retraits décidés", "4") in sections[1][1]
    data["fives"] = {"bytes": 3 * 1024 ** 4, "folders_measured": 9, "growth_bytes": 5 * 1024 ** 3, "duplicate_bytes": 0, "cold_3y_bytes": 0,
                     "score": 61, "quarantined": {"files": 2, "bytes": 1024}, "archived": 1, "partial_measures": 0}
    five = dict(monthly_report.lines(data)[-1][1])
    assert five["Volume mesuré"] == "3 To (9 dossier(s))" and five["Croissance du mois"] == "+5 Go" and five["Score 5S moyen"] == "61 / 100"


def test_the_report_goes_once_on_the_first_of_the_month(monkeypatch) -> None:
    from app.services import notifications

    sent = []
    monkeypatch.setattr(notifications, "settings", lambda db: {"enabled": True, "monthlyReport": True})
    monkeypatch.setattr(notifications, "_already_sent", lambda db, key: key in {"monthly_report:2026-10"})
    monkeypatch.setattr(monthly_report, "send", lambda db, **kw: sent.append(kw["key"]) or {})
    assert monthly_report.maybe_send(None, datetime(2026, 11, 2)) is False          # not the 1st
    assert monthly_report.maybe_send(None, datetime(2026, 11, 1)) is False          # already sent for October
    assert monthly_report.maybe_send(None, datetime(2026, 12, 1)) is True and sent == ["monthly_report:2026-11"]
    monkeypatch.setattr(notifications, "settings", lambda db: {"enabled": True, "monthlyReport": False})
    assert monthly_report.maybe_send(None, datetime(2027, 1, 1)) is False           # switched off
