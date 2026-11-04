from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.actions.folder import parse_ls_folders

LS = """  .                                   D        0  Tue Nov  4 10:00:00 2026
  ..                                  D        0  Tue Nov  4 10:00:00 2026
  Finance                             D        0  Mon Nov  3 09:12:00 2026
  Ressources humaines                 D        0  Mon Nov  3 09:12:00 2026
  Archives                           DH        0  Mon Nov  3 09:12:00 2026
  budget.xlsx                         A    12034  Mon Nov  3 09:12:00 2026

		51097599 blocks of size 4096. 37245810 blocks available
"""


def test_only_the_folders_are_kept() -> None:
    assert parse_ls_folders(LS) == ["Archives", "Finance", "Ressources humaines"]
    assert parse_ls_folders("NT_STATUS_ACCESS_DENIED listing \\\\x") == []
