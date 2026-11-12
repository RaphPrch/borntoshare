from app.services.scans import emptied


def test_an_empty_measure_never_replaces_a_full_one() -> None:
    assert emptied({"content_stats": {"files": 143859}}, {"files": 0, "bytes": 0})
    assert not emptied({"content_stats": {"files": 143859}}, {"files": 120000})
    # A folder measured for the first time, or really empty before: nothing to protect
    assert not emptied({}, {"files": 0}) and not emptied({"content_stats": {"files": 0}}, {"files": 0})
