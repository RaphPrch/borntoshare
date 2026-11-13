"""A folder declared inside a measured one gets its part of the measure and of the sensitivity scan."""
from __future__ import annotations

from types import SimpleNamespace

from app.services import derived_measure as dm


def _root(root_id, path, measured=True, derived=False):
    stats = {"files": 10, **({"method": "derived"} if derived else {})}
    return SimpleNamespace(id=root_id, root_path=path, storage_endpoint_id=1,
                           discovered_permissions_json={"content_stats": stats} if measured else {"content_size_bytes": 1})


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *a, **k):
        return self

    def all(self):
        return self.rows


class _Db:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        return _Query(self.rows)


def test_closest_measured_ancestor_from_a_real_measure():
    share = _root(1, "\\\\filer\\DATA")
    middle = _root(2, "\\\\filer\\DATA\\TRASH", measured=False)
    derived = _root(3, "\\\\filer\\DATA\\TRASH\\A", derived=True)
    other = _root(4, "\\\\filer\\DATA2")
    child = _root(5, "\\\\filer\\DATA\\TRASH\\A\\B", measured=False)
    assert dm.ancestor_of(_Db([share, middle, derived, other, child]), child) is share
    assert dm.ancestor_of(_Db([other, child]), child) is None


def test_child_findings_keep_the_child_part_with_paths_from_the_child():
    findings = [{"path": "Images IRM Raph\\2024\\scan.dcm", "category": "personal_data"},
                {"path": "TRASH\\mdp.txt", "category": "password"},
                {"path": "Images IRM Raph Copie\\x.txt", "category": "password"}]
    mine = dm.child_findings(findings, "\\\\filer\\DATA", "\\\\filer\\DATA\\Images IRM Raph")
    assert mine == [{"path": "2024\\scan.dcm", "category": "personal_data"}]
    # A parent inside its share: its findings are from the parent
    mine = dm.child_findings([{"path": "Budget\\mdp.txt", "category": "password"}], "\\\\filer\\Angers\\Finance", "\\\\filer\\Angers\\Finance\\Budget")
    assert mine == [{"path": "mdp.txt", "category": "password"}]
