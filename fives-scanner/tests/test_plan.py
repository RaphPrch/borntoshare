from scanner.runner import in_window, plan

LOCAL = "C:\\Shares\\Finance"


def test_first_scan_or_no_journal_is_full() -> None:
    assert plan(chunks=["A", "B"], known=set(), state=None, journal=None, local=LOCAL, full_due=False) == ("full", {"", "A", "B"})
    assert plan(chunks=["A"], known={"", "A"}, state={"x": 1}, journal={"changed": None}, local=LOCAL, full_due=False)[0] == "full"


def test_only_the_changed_pieces_and_the_new_ones() -> None:
    mode, todo = plan(chunks=["A", "B", "C"], known={"", "A", "B"}, state={"x": 1},
                      journal={"changed": ["C:\\Shares\\Finance\\B\\2025", "C:\\Shares\\Other\\Z"]}, local=LOCAL, full_due=False)
    assert mode == "incremental" and todo == {"B", "C"}


def test_a_full_walk_when_it_is_due() -> None:
    assert plan(chunks=["A"], known={"", "A"}, state={"x": 1}, journal={"changed": []}, local=LOCAL, full_due=True)[0] == "full"


def test_window_over_midnight() -> None:
    from datetime import datetime

    values = {"window_start": "20:00", "window_end": "06:00", "timezone": "UTC"}
    assert in_window(values, datetime(2026, 11, 9, 22, 0)) and in_window(values, datetime(2026, 11, 9, 5, 59))
    assert not in_window(values, datetime(2026, 11, 9, 12, 0))
