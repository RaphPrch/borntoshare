"""A pending request waiting longer than its decision deadline is overdue: in the list (flag and filter) and on the dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.data.repositories import access_requests_views_repo as repo
from app.data.repositories.access_requests_views_repo import AccessRequestsViewsRepo, DEFAULT_DECISION_DAYS, due_at, is_overdue

NOW = datetime(2026, 11, 24, 12, 0, 0)


def test_only_a_pending_request_older_than_the_delay_is_overdue() -> None:
    old = NOW - timedelta(days=DEFAULT_DECISION_DAYS, hours=1)
    young = NOW - timedelta(days=DEFAULT_DECISION_DAYS - 1)
    assert is_overdue({"status": "pending", "created_at": old}, NOW) is True
    assert is_overdue({"status": "PENDING", "created_at": old.isoformat() + "Z"}, NOW) is True
    assert is_overdue({"status": "pending", "created_at": young}, NOW) is False
    assert is_overdue({"status": "approved", "created_at": old}, NOW) is False
    assert is_overdue({"status": "pending", "created_at": None}, NOW) is False


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return [dict(row) for row in self.rows]


class _Db:
    """The view answers the first query; the later reads (decisions, names) find nothing."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0
        self.params = None

    def execute(self, _sql, params=None, **kwargs):
        self.calls += 1
        self.params = self.params or params
        return _Result(self.rows if self.calls == 1 else [])


def test_the_overdue_filter_keeps_the_overdue_requests(monkeypatch) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [{"request_id": 1, "status": "pending", "created_at": now - timedelta(days=DEFAULT_DECISION_DAYS + 2), "storage_root_name": "Finance"},
            {"request_id": 2, "status": "pending", "created_at": now, "storage_root_name": "RH"}]
    # The enrichment after the query reads other tables: not under test here
    monkeypatch.setattr(AccessRequestsViewsRepo, "_fetch_requests_snapshot", lambda self, ids: {})
    monkeypatch.setattr(AccessRequestsViewsRepo, "_enrich_row", lambda self, row, snapshot: row)
    monkeypatch.setattr(AccessRequestsViewsRepo, "_fetch_guardian_names_by_root", lambda self, ids: {})
    view = AccessRequestsViewsRepo.__new__(AccessRequestsViewsRepo)
    view.db = _Db(rows)
    listed = view.list(overdue_only=True)
    assert [row["request_id"] for row in listed] == [1] and listed[0]["overdue"] is True
    # Filtered on pending in SQL, before the 200-row limit
    assert view.db.params["status"] == "pending"
    view.db = _Db(rows)
    assert [row["overdue"] for row in view.list()] == [True, False]
    assert repo.DEFAULT_DECISION_DAYS == 3


def test_the_decision_deadline_follows_the_setting() -> None:
    made = NOW - timedelta(days=4)
    row = {"status": "pending", "created_at": made}
    assert is_overdue(row, NOW, 3) is True
    assert is_overdue(row, NOW, 7) is False
    assert due_at(row, 7) == made + timedelta(days=7)
    assert due_at({"status": "approved", "created_at": made}, 7) is None
