from app.services.scans import emptied


def test_an_empty_measure_never_replaces_a_full_one() -> None:
    assert emptied({"content_stats": {"files": 143859}}, {"files": 0, "bytes": 0})
    assert not emptied({"content_stats": {"files": 143859}}, {"files": 120000})
    # A folder measured for the first time, or really empty before: nothing to protect
    assert not emptied({}, {"files": 0}) and not emptied({"content_stats": {"files": 0}}, {"files": 0})


def test_the_last_three_measures_are_kept() -> None:
    from app.services.scans import with_previous

    current = {"content_stats": {"files": 4}, "content_size_bytes": 40, "content_updated_at": "d4",
               "content_previous": [{"at": "d3", "stats": {"files": 3}}, {"at": "d2", "stats": {"files": 2}}, {"at": "d1", "stats": {"files": 1}}]}
    history = with_previous(current)
    assert [item["at"] for item in history] == ["d4", "d3", "d2"] and history[0]["bytes"] == 40
    assert with_previous({}) == []
