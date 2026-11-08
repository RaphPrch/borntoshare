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
