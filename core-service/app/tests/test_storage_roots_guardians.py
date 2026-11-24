"""Guardians of the folders in /storage-roots/context: names and logins mixed (express search), one entry per guardian."""

from __future__ import annotations

from app.data.repositories.storage_roots_views_repo import StorageRootsViewsRepo


def _repo(rows: list[dict]) -> StorageRootsViewsRepo:
    repo = StorageRootsViewsRepo.__new__(StorageRootsViewsRepo)
    repo._all = lambda sql, params: rows  # type: ignore[method-assign]
    return repo


def test_each_guardian_comes_with_its_login_and_name() -> None:
    repo = _repo([
        {"root_id": 1, "identity_id": 7, "name": "Alice Martin", "username": "amartin"},
        {"root_id": 1, "identity_id": 9, "name": "bdupont", "username": "bdupont", "has_backup": 1},
        {"root_id": 2, "identity_id": 7, "name": "Alice Martin", "username": "amartin"},
    ])
    names, guardians = repo._load_guardian_names([1, 2])
    assert names[1] == ["Alice Martin", "amartin", "bdupont"]
    # has_backup: a backup guardian stands in for them now (coverage of the folder)
    assert guardians[1] == [{"identity_id": 7, "login": "amartin", "name": "Alice Martin", "has_backup": False},
                            {"identity_id": 9, "login": "bdupont", "name": "bdupont", "has_backup": True}]
    assert guardians[2] == [{"identity_id": 7, "login": "amartin", "name": "Alice Martin", "has_backup": False}]


def test_no_folder_no_query() -> None:
    assert _repo([])._load_guardian_names([]) == ({}, {})
