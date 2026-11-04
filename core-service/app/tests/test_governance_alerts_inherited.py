from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.data.repositories import governance_alerts_repo as repo


def _acl(*raws: str) -> dict:
    return {"permissions": [{"principal": "BUILTIN\\Utilisateurs", "raw": raw} for raw in raws]}


class _DB:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_args, **_kwargs):
        rows = self.rows

        class _Result:
            def mappings(self):
                return self

            def all(self):
                return rows

        return _Result()


def _normalize(value):
    return str(value or "").replace("/", "\\").lower().split("\\")[-1]


def test_inherited_flag_comes_from_the_smbcacls_flags() -> None:
    assert repo._is_inherited({"raw": "ALLOWED/OI|CI|I/READ"})
    assert not repo._is_inherited({"raw": "ALLOWED/OI|CI/READ"})
    assert not repo._is_inherited({"raw": ""})


def test_one_folder_of_the_share_holds_the_inherited_alert() -> None:
    rows = [
        {"id": 12, "root_path": "\\\\filer\\Paris\\Finance", "discovered_permissions_json": _acl("ALLOWED/OI|CI|I/READ")},
        {"id": 11, "root_path": "\\\\filer\\Paris\\RH", "discovered_permissions_json": _acl("ALLOWED/OI|CI|I/READ")},
        {"id": 13, "root_path": "\\\\filer\\Paris\\RH\\Paie", "discovered_permissions_json": _acl("ALLOWED/OI|CI|I/READ")},
        # Explicit only: the folder has its own alert, not this one
        {"id": 10, "root_path": "\\\\filer\\Paris\\Achats", "discovered_permissions_json": _acl("ALLOWED/OI|CI/READ")},
        # Another share
        {"id": 5, "root_path": "\\\\filer\\Lyon\\RH", "discovered_permissions_json": _acl("ALLOWED/OI|CI|I/READ")},
    ]
    alerts = repo.GovernanceAlertsRepo.__new__(repo.GovernanceAlertsRepo)
    alerts.db = _DB(rows)
    share, holders = alerts._inherited_holders(
        endpoint_id=90, root_path="\\\\filer\\Paris\\RH\\Paie", principal="utilisateurs", normalize=_normalize
    )
    assert share == "\\\\filer\\Paris"
    # Highest folders first, then the oldest: Paris\RH (11) holds the alert for the 3 folders
    assert holders == [11, 12, 13]
