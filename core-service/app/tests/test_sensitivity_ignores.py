from __future__ import annotations

from app.services.sensitivity import visible

FINDINGS = [
    {"path": "IT\\coffre.kdbx", "category": "password_vault"},
    {"path": "IT\\web.config", "category": "password"},
    {"path": "IT\\mdp.txt", "category": "credentials_file"},
    {"path": "IT\\mdp.txt", "category": "password"},
]


def test_a_false_positive_no_longer_counts():
    assert visible(FINDINGS, set()) == (3, {"password_vault": 1, "password": 2, "credentials_file": 1})
    assert visible(FINDINGS, {"it\\mdp.txt"}) == (2, {"password_vault": 1, "password": 1})


def test_files_beyond_the_listed_findings_still_count():
    # The worker keeps 100 findings at most: 120 flagged files, 3 listed, 1 of them ignored
    assert visible(FINDINGS, {"it\\web.config"}, total_flagged=120)[0] == 119
