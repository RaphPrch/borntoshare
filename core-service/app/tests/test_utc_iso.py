"""utc_iso: one way to send a database time to the browser (naive UTC → « Z »)."""
from datetime import datetime, timedelta, timezone

from app.core.values import utc_iso


def test_naive_database_times_get_their_z() -> None:
    assert utc_iso(datetime(2026, 11, 26, 10, 30)) == "2026-11-26T10:30:00Z"
    # An aware time keeps its offset (never a second suffix)
    assert utc_iso(datetime(2026, 11, 26, 10, 30, tzinfo=timezone.utc)) == "2026-11-26T10:30:00+00:00"
    assert utc_iso(datetime(2026, 11, 26, 10, 30, tzinfo=timezone(timedelta(hours=1)))) == "2026-11-26T10:30:00+01:00"


def test_nothing_and_text() -> None:
    assert utc_iso(None) is None and utc_iso("") is None
    # Already a string (a JSON payload read back): as it is
    assert utc_iso("2026-11-26T10:30:00Z") == "2026-11-26T10:30:00Z"
