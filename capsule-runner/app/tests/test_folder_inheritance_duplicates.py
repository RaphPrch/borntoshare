from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.actions.folder import explicit_duplicates


def test_the_copies_of_inherited_entries_are_found() -> None:
    # A folder of the lab after a break (copies) then a restore (inherited entries back)
    acl = [
        "ACL:AUTORITE NT\\Système:ALLOWED/OI|CI/FULL",
        "ACL:BUILTIN\\Utilisateurs:ALLOWED/CI/0x00000002",
        "ACL:CORP\\GG_Paris_RW:ALLOWED/OI|CI/CHANGE",
        "ACL:AUTORITE NT\\Système:ALLOWED/OI|CI|I/FULL",
        "ACL:BUILTIN\\Utilisateurs:ALLOWED/CI|I/0x00000002",
        "ACL:BUILTIN\\Utilisateurs:ALLOWED/OI|CI|I/READ",
    ]
    assert explicit_duplicates(acl) == [
        "ACL:AUTORITE NT\\Système:ALLOWED/OI|CI/FULL",
        "ACL:BUILTIN\\Utilisateurs:ALLOWED/CI/0x00000002",
    ]


def test_an_explicit_right_that_differs_stays() -> None:
    acl = [
        "ACL:BUILTIN\\Utilisateurs:ALLOWED/OI|CI/CHANGE",  # more than the inherited READ
        "ACL:BUILTIN\\Utilisateurs:DENIED/OI|CI/READ",  # another type
        "ACL:BUILTIN\\Utilisateurs:ALLOWED/OI|CI|I/READ",
    ]
    assert explicit_duplicates(acl) == []
