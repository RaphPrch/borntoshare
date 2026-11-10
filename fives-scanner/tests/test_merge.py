from scanner.merge import chunk_of, merge


def _chunk(bytes_, files, **extra):
    return {"bytes": bytes_, "files": files, "folders": 1, "types": [{"ext": "pdf", "files": files}],
            "cold": {"1y": {"bytes": bytes_ // 2, "files": 1}, "3y": {"bytes": 0, "files": 0}}, "junk": {"bytes": 1, "files": 1, "examples": ["x"]},
            "duplicates": {"groups": 0, "files": 0, "wasted_bytes": 0, "top": []}, "fingerprints": [], **extra}


def test_a_folder_is_the_sum_of_its_chunks() -> None:
    stats = merge({"": _chunk(10, 1, folders=0), "2025": _chunk(100, 4, last_modified="2026-01-02T00:00:00Z"),
                   "Archives": _chunk(1000, 2, last_modified="2025-01-01T00:00:00Z")})
    assert (stats["bytes"], stats["files"], stats["folders"]) == (1110, 7, 4)  # 2 chunks + 1 sub-folder in each
    assert [item["name"] for item in stats["top"]] == ["Archives", "2025"]
    assert stats["types"] == [{"ext": "pdf", "files": 7}] and stats["cold"]["1y"]["bytes"] == 555
    assert stats["last_modified"] == "2026-01-02T00:00:00Z" and stats["junk"]["files"] == 3


def test_a_file_in_two_chunks_is_a_duplicate_once() -> None:
    fp = {"fingerprint": "aa", "size": 5000}
    stats = merge({"A": _chunk(5000, 1, fingerprints=[{**fp, "path": "F\\A\\x.zip"}]),
                   "B": _chunk(5000, 1, fingerprints=[{**fp, "path": "F\\B\\x.zip"}],
                               duplicates={"groups": 1, "files": 2, "wasted_bytes": 300, "top": [{"size": 300, "files": 2, "wasted": 300, "paths": []}]})})
    assert stats["duplicates"]["wasted_bytes"] == 5300 and stats["duplicates"]["groups"] == 2
    assert stats["duplicates"]["top"][0]["paths"] == ["F\\A\\x.zip", "F\\B\\x.zip"]


def test_changed_folders_map_to_their_chunk() -> None:
    local = "C:\\Shares\\Finance"
    assert chunk_of("C:\\Shares\\Finance\\2025\\T1", local) == "2025"
    assert chunk_of("c:\\shares\\finance", local) == ""
    assert chunk_of("C:\\Shares\\Financement", local) is None
