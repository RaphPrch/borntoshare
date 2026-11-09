from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.actions.smb import parse_recursive_ls

LS = """  .                                   D        0  Tue Nov  4 10:00:00 2026
  ..                                  D        0  Tue Nov  4 10:00:00 2026
  2025                                D        0  Mon Nov  3 09:12:00 2026
  Archives                            D        0  Mon Nov  3 09:12:00 2026
  note.txt                            A      100  Mon Nov  3 09:12:00 2026

\\Paris\\Finance\\2025
  .                                   D        0  Mon Nov  3 09:12:00 2026
  ..                                  D        0  Mon Nov  3 09:12:00 2026
  T1                                  D        0  Mon Nov  3 09:12:00 2026
  budget 2025.xlsx                    A     5000  Mon Nov  3 09:12:00 2026

\\Paris\\Finance\\2025\\T1
  bilan.pdf                           A     2000  Mon Nov  3 09:12:00 2026
  scan.pdf                            A     1000  Mon Nov  3 09:12:00 2026

\\Paris\\Finance\\Archives
  vieux.zip                           A      300  Mon Nov  3 09:12:00 2026

		51097599 blocks of size 4096. 37245810 blocks available
"""


def test_totals_top_folders_and_types() -> None:
    stats = parse_recursive_ls(LS, base="Paris\\Finance")
    assert (stats["bytes"], stats["files"], stats["folders"]) == (8400, 5, 3)
    assert stats["top"][0] == {"name": "2025", "bytes": 8000, "files": 3}
    assert {"name": "Archives", "bytes": 300, "files": 1} in stats["top"]
    assert stats["types"][0] == {"ext": "pdf", "files": 2}
    assert stats["truncated"] is False


def test_a_huge_listing_is_a_floor() -> None:
    assert parse_recursive_ls(LS, max_entries=2, base="Paris\\Finance")["truncated"] is True


AGED = """  .                                   D        0  Tue Nov  4 10:00:00 2026
  recent.docx                         A      100  Mon Nov  2 09:12:00 2026
  Thumbs.db                           AH      20  Mon Nov  2 09:12:00 2026
  ~$budget.xlsx                       AH      10  Mon Nov  2 09:12:00 2026

\\Archives
  projet 2024.zip                     A     5000  Fri Mar  1 09:12:00 2024
  projet 2021.zip                     A     9000  Mon Mar  1 09:12:00 2021
  Rapport - Copie.pdf                 A      300  Mon Mar  1 09:12:00 2021
"""


def test_age_of_the_data_and_the_clutter() -> None:
    now = parse_recursive_ls.__globals__["datetime"](2026, 11, 9).timestamp()
    stats = parse_recursive_ls(AGED, now=now)
    assert stats["cold"]["1y"] == {"bytes": 14300, "files": 3}
    assert stats["cold"]["3y"] == {"bytes": 9300, "files": 2}
    # smbclient writes local times: the same instant, in UTC, whatever the TZ of the worker
    utc = lambda *parts: parse_recursive_ls.__globals__["datetime"].fromtimestamp(  # noqa: E731
        parse_recursive_ls.__globals__["datetime"](*parts).timestamp(), tz=parse_recursive_ls.__globals__["timezone"].utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert stats["cold_top"][0] == {"path": "Archives\\projet 2021.zip", "bytes": 9000, "modified": utc(2021, 3, 1, 9, 12)}
    assert stats["junk"]["files"] == 3 and stats["junk"]["bytes"] == 330
    assert "Archives\\Rapport - Copie.pdf" in stats["junk"]["examples"]
    assert stats["last_modified"] == utc(2026, 11, 2, 9, 12)
