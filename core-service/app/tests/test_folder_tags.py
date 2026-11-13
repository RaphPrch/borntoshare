"""Policies « also on the sub-folders »: which criteria, which sub-folders."""
from __future__ import annotations

import json

from app.services import folder_tags


class _Row:
    def __init__(self, values):
        self.values = values

    def first(self):
        return self.values


class _Db:
    def __init__(self, findings=None, ignored=None):
        self.findings, self.ignored = findings or [], ignored or []

    def execute(self, statement, params=None):
        return _Row((json.dumps(self.findings), json.dumps(self.ignored)))


def test_supported_criteria():
    assert folder_tags.supported("chemin:irm")
    assert folder_tags.supported("est:mot-de-passe chemin:compta")
    assert folder_tags.supported("-chemin:archives est:sensible")
    assert not folder_tags.supported("taille>1Go")
    assert not folder_tags.supported("doublons>10Go")
    assert not folder_tags.supported("irm")  # free text
    assert not folder_tags.supported("")


def test_name_match_tags_the_folder_not_its_children(monkeypatch):
    from app.services import modules

    monkeypatch.setattr(modules, "folder_paths", lambda root_id: ["TRASH", "Images IRM Raph", "Images IRM Raph\\2024", "Radiologie\\IRM genou"])
    row = {"storage_root_id": 45, "root_path": "\\\\filer\\DATA"}
    assert folder_tags.matching_folders(_Db(), row, "chemin:irm") == ["Images IRM Raph", "Radiologie\\IRM genou"]


def test_sensitive_files_tag_the_folder_that_holds_them():
    findings = [{"path": "Informatique\\Scripts\\deploy.ps1", "category": "password"},
                {"path": "Informatique\\wifi.txt", "category": "credentials_file"},
                {"path": "RH\\paie.xlsx", "category": "personal_data"},
                {"path": "Test\\faux.txt", "category": "password"}]
    row = {"storage_root_id": 1, "root_path": "\\\\filer\\Angers"}
    db = _Db(findings, ignored=[{"path": "Test\\faux.txt"}])
    assert folder_tags.matching_folders(db, row, "est:mot-de-passe") == ["Informatique", "Informatique\\Scripts"]
    assert folder_tags.matching_folders(db, row, "est:donnees-personnelles") == ["RH"]


def test_paths_of_a_folder_inside_a_share_are_from_the_share():
    row = {"storage_root_id": 2, "root_path": "\\\\filer\\Angers\\Finance"}
    db = _Db([{"path": "Budget\\mdp.txt", "category": "password"}])
    assert folder_tags.matching_folders(db, row, "est:mot-de-passe") == ["Finance\\Budget"]


def test_system_folders_are_never_tagged():
    findings = [{"path": "$RECYCLE.BIN\\$R1\\mdp.txt", "category": "password"}, {"path": "~BROMIUM\\x.txt", "category": "password"},
                {"path": "Docs\\mdp.txt", "category": "password"}]
    row = {"storage_root_id": 3, "root_path": "\\\\filer\\DATA"}
    assert folder_tags.matching_folders(_Db(findings), row, "est:mot-de-passe") == ["Docs"]
