from __future__ import annotations

import logging

from app.services import log_retention


def test_log_level_names_of_the_ui_apply_to_core() -> None:
    assert log_retention.apply_log_level("WARN") == "WARNING"
    assert logging.getLogger().level == logging.WARNING
    assert log_retention.apply_log_level("nonsense") == "INFO"
    log_retention.apply_log_level("INFO")


def test_daily_purge_runs_once_a_day_and_only_when_enabled(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(log_retention, "purge_logs", lambda db, **kw: calls.append(kw) or {"ok": True})
    monkeypatch.setattr(log_retention, "_last_auto_purge", 0.0)

    monkeypatch.setattr(log_retention, "logging_settings", lambda db: {"retentionEnabled": False, "retentionDays": 30, "level": "INFO"})
    assert log_retention.auto_purge_if_due(object()) is None

    monkeypatch.setattr(log_retention, "_last_auto_purge", 0.0)
    monkeypatch.setattr(log_retention, "logging_settings", lambda db: {"retentionEnabled": True, "retentionDays": 30, "level": "INFO"})
    assert log_retention.auto_purge_if_due(object()) == {"ok": True}
    assert calls == [{"days": 30, "trigger": "schedule"}]
    # Same day: nothing more
    assert log_retention.auto_purge_if_due(object()) is None


class _Session:
    def __init__(self, counts):
        self.counts = list(counts)
        self.sql = []

    def execute(self, statement, params=None):
        self.sql.append(str(statement))

        class _R:
            rowcount = self.counts.pop(0) if self.counts else 0

        return _R()

    def commit(self):
        pass


def test_old_rows_are_deleted_in_batches() -> None:
    session = _Session([log_retention.BATCH, 12])
    assert log_retention._delete_older(session, "audit_event", "event_time", 180) == log_retention.BATCH + 12
    assert all("LIMIT" in sql and "INTERVAL :days DAY" in sql for sql in session.sql)
