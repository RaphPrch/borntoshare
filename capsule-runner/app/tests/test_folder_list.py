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


def test_parse_ls_files_keeps_files_with_size_and_date():
    from app.actions.folder import parse_ls_files

    output = "\n".join([
        "  .                                   D        0  Thu Nov 12 10:00:00 2026",
        "  ..                                  D        0  Thu Nov 12 10:00:00 2026",
        "  Archives 2020                       D        0  Mon Jan  6 09:15:02 2020",
        "  rapport final  v2.docx              A    48213  Tue Mar  3 08:01:59 2026",
        "  photo.jpg                           N  2048576  Sun Dec 25 23:59:01 2022",
        "  sans-attribut.txt                          12  Wed Jul  1 07:00:00 2026",
        "",
        "\t\t51175 blocks of size 4194304. 9786 blocks available",
    ])
    files = parse_ls_files(output)
    assert [f["n"] for f in files] == ["rapport final  v2.docx", "photo.jpg", "sans-attribut.txt"]
    assert files[1]["s"] == 2048576 and files[1]["t"] == "2022-12-25T23:59:01"
    assert files[2]["s"] == 12
