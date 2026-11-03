from __future__ import annotations

from types import SimpleNamespace

from app.actions import dfs_namespaces as dfs

BASE = {"path": "\\\\corp.local\\brest", "username": "CORP\\svc", "password": "x"}
INFO = "path: \\\\CORP.LOCAL\\brest\\Corporate\\Finance\n\tstorage[0] server: FILER01\n\tstorage[0] share: Finance\n"


def _fake(monkeypatch, *outputs):
    calls: list[str] = []
    queue = list(outputs)
    monkeypatch.setattr(dfs, "_root_server", lambda path, **_: ("DFS01.CORP.LOCAL", "brest"))
    monkeypatch.setattr(dfs, "resolve", lambda host: "10.0.0.5")

    def run_samba(cmd, **_):
        calls.append(cmd[-1])
        return SimpleNamespace(stdout=(queue.pop(0) if queue else "").encode(), stderr=b"", returncode=0)

    monkeypatch.setattr(dfs, "run_samba", run_samba)
    return calls


def test_creates_the_folder_on_the_root_server_and_reads_it_back(monkeypatch) -> None:
    calls = _fake(monkeypatch, "result was WERR_NOT_FOUND", "", INFO)
    ok, _, details = dfs.dfs_folder_create({**BASE, "folder": "Corporate\\Finance", "target_unc": "\\\\FILER01\\Finance"})
    assert ok is True and details["server"] == "DFS01.CORP.LOCAL"
    assert calls[1] == 'dfsadd "\\\\corp.local\\brest\\Corporate\\Finance" "FILER01" "Finance" "BornToShare"'


def test_an_existing_target_is_reported(monkeypatch) -> None:
    _fake(monkeypatch, INFO)
    ok, _, details = dfs.dfs_folder_create({**BASE, "folder": "Corporate\\Finance", "target_unc": "\\\\FILER01\\Finance"})
    assert ok is False and details["failure_code"] == "DFS_FOLDER_EXISTS"


def test_an_account_without_delegation_gets_a_clear_message(monkeypatch) -> None:
    _fake(monkeypatch, "", "result was WERR_ACCESS_DENIED", "")
    ok, message, details = dfs.dfs_folder_create({**BASE, "folder": "Finance", "target_unc": "\\\\FILER01\\Finance"})
    assert ok is False and details["failure_code"] == "DFS_ADMIN_REQUIRED" and "delegate" in message


def test_invalid_names_and_targets_reach_nothing(monkeypatch) -> None:
    calls = _fake(monkeypatch)
    for folder in ("", "a\\..\\b", "Fin:ance", "Fin|ance"):
        assert dfs.dfs_folder_create({**BASE, "folder": folder, "target_unc": "\\\\FILER01\\Finance"})[2]["failure_code"] == "DFS_FOLDER_INVALID"
    assert dfs.dfs_folder_create({**BASE, "folder": "Finance", "target_unc": "FILER01\\Finance"})[2]["failure_code"] == "DFS_TARGET_INVALID"
    assert calls == []


def test_removes_every_target(monkeypatch) -> None:
    calls = _fake(monkeypatch, "", "", "", "")
    ok, _, _ = dfs.dfs_folder_delete({**BASE, "folder": "Corporate\\Finance", "targets": ["\\\\FILER01\\Finance", "\\\\FILER02\\Finance"]})
    assert ok is True
    assert [c for c in calls if c.startswith("dfsremove")] == [
        'dfsremove "\\\\corp.local\\brest\\Corporate\\Finance" "FILER01" "Finance"',
        'dfsremove "\\\\corp.local\\brest\\Corporate\\Finance" "FILER02" "Finance"',
    ]


def test_a_target_still_there_is_a_failure(monkeypatch) -> None:
    _fake(monkeypatch, "result was WERR_ACCESS_DENIED", INFO)
    ok, _, details = dfs.dfs_folder_delete({**BASE, "folder": "Corporate\\Finance", "targets": ["\\\\FILER01\\Finance"]})
    assert ok is False and details["failure_code"] == "DFS_ADMIN_REQUIRED"


def test_a_job_shaped_payload_validates_for_both_actions() -> None:
    from app.core import action_registry as registry

    for slug, target in (
        ("dfs_folder_delete", {"host": "DFS01", "path": "\\\\corp.local\\brest", "folder": "Finance", "targets": ["\\\\FILER01\\Finance"]}),
        ("dfs_folder_create", {"host": "DFS01", "path": "\\\\corp.local\\brest", "folder": "Finance", "target_unc": "\\\\FILER01\\Finance"}),
    ):
        spec = registry.ALLOWED_ACTIONS[slug]
        flat = registry._flatten_inputs_payload({"target": target, "auth": {"username": "CORP\\svc", "secret_ref": "sm://x/y"}, "options": {"timeout_sec": 60}})
        spec.schema.model_validate({k: v for k, v in flat.items() if k in spec.schema.model_fields})
