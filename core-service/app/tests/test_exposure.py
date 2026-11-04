from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.exposure import _share_of, classify


def _ace(principal: str, raw: str) -> dict:
    return {"principal": principal, "raw": raw}


def _level(aces, **extra) -> str:
    return classify(aces, scanned=True, governed=extra.get("governed", {"gg_rh_r"}), accepted=extra.get("accepted", set()), service_account="CORP\\b2s")["level"]


SYSTEM = [_ace("AUTORITE NT\\Système", "ALLOWED/OI|CI|I/FULL"), _ace("CORP\\b2s", "ALLOWED/OI|CI/FULL")]


def test_levels_from_the_acl() -> None:
    assert _level(SYSTEM + [_ace("CORP\\GG_RH_R", "ALLOWED/OI|CI/READ")]) == "governed"
    assert _level(SYSTEM + [_ace("CORP\\paul.martin", "ALLOWED/OI|CI/READ")]) == "outside"
    assert _level(SYSTEM + [_ace("BUILTIN\\Utilisateurs", "ALLOWED/OI|CI|I/READ")]) == "open_read"
    assert _level(SYSTEM + [_ace("Tout le monde", "ALLOWED/OI|CI/CHANGE"), _ace("BUILTIN\\Utilisateurs", "ALLOWED/OI|CI/READ")]) == "open_write"


def test_accepted_gaps_and_denials_do_not_open_a_folder() -> None:
    assert _level(SYSTEM + [_ace("BUILTIN\\Utilisateurs", "ALLOWED/OI|CI/READ")], accepted={"builtin\\utilisateurs"}) == "governed"
    assert _level(SYSTEM + [_ace("Tout le monde", "DENIED/OI|CI/FULL")]) == "governed"
    assert classify([], scanned=False, governed=set(), accepted=set(), service_account=None)["level"] == "unknown"


def test_share_of_a_folder() -> None:
    assert _share_of("\\\\filer\\Paris\\RH\\Paie") == "\\\\filer\\Paris"
