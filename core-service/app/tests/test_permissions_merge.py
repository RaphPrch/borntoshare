from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.storage_root_permissions import merge_by_principal


def _entry(principal: str, rights: str, inherited: bool) -> dict:
    return {"principal": principal, "rights": rights, "rights_label": rights, "level": None, "raw": "", "inherited": inherited, "inherited_scope": True}


def test_one_line_per_account_with_the_strongest_right_and_its_origin() -> None:
    rows = merge_by_principal([
        _entry("BUILTIN\\Utilisateurs", "special", False),
        _entry("BUILTIN\\Utilisateurs", "read", True),
        _entry("BUILTIN\\Utilisateurs", "special", True),
        _entry("AUTORITE NT\\Système", "full", True),
    ])
    by_name = {row["principal"]: row for row in rows}
    assert len(rows) == 2
    assert by_name["BUILTIN\\Utilisateurs"]["rights"] == "read" and by_name["BUILTIN\\Utilisateurs"]["origin"] == "both"
    assert by_name["AUTORITE NT\\Système"]["origin"] == "inherited"
