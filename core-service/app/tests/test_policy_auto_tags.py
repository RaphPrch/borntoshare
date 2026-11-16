from app.services import policies, sensitivity


import pytest
from fastapi import HTTPException

from app.services import activity_log


class _Result:
    def __init__(self, rows=None, rowcount=0, scalar=None):
        self.rows, self.rowcount, self._scalar = rows or [], rowcount, scalar

    def scalar(self):
        return self._scalar

    def all(self):
        return self.rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class _Db:
    """Hits of the policy before the run: folders 1 and 2; the run sees only folder 1 matching."""

    def __init__(self, tag_name="Mots de passe", hits=((1,), (2,))):
        self.sql, self.tag_name, self.hits = [], tag_name, list(hits)

    def execute(self, statement, params=None):
        text = " ".join(str(statement).split())
        self.sql.append((text, params))
        if text.startswith("SELECT storage_root_id FROM governance_policy_hits"):
            return _Result(self.hits)
        if text.startswith("SELECT name FROM tags"):
            return _Result(scalar=self.tag_name)
        if text.startswith("SELECT storage_root_id FROM storage_root_tags"):
            return _Result([(2,)])  # folder 2 carries the tag
        if text.startswith("INSERT IGNORE INTO storage_root_tags"):
            return _Result(rowcount=1)
        if text.startswith("DELETE FROM storage_root_tags"):
            return _Result(rowcount=len(params["ids"]))
        return _Result()

    def commit(self):
        pass


@pytest.fixture(autouse=True)
def _events(monkeypatch):
    logged = []
    monkeypatch.setattr(activity_log, "log_activity", lambda _db, **kw: logged.append(kw))
    return logged


def _run(actions, db=None):
    db = db or _Db()
    rows = [{"storage_root_id": 1, "storage_root_name": "Compta", "password_files": 1}, {"storage_root_id": 2, "storage_root_name": "RH", "password_files": 0}]
    out = policies.run_policy(db, {"id": 7, "name": "p", "condition": "est:mot-de-passe", "actions": actions}, rows, allow_jobs=False)
    return db, out


def test_an_automatic_tag_goes_with_the_condition() -> None:
    db, out = _run({"add_tag": 5, "remove_tag": True})
    removed = [params for text, params in db.sql if text.startswith("DELETE FROM storage_root_tags")]
    assert removed == [{"tag": 5, "ids": [2]}] and out["untagged"] == 1


def test_a_tag_stays_without_the_option() -> None:
    db, out = _run({"add_tag": 5})
    assert not any(text.startswith("DELETE FROM storage_root_tags") for text, _params in db.sql) and out["untagged"] == 0


def test_file_groups_cover_the_new_categories() -> None:
    assert sensitivity.FILE_GROUPS["personal_files"] == ("personal_data",)
    assert sensitivity.FILE_GROUPS["bank_files"] == ("bank_data",)
    assert set(sensitivity.FILE_GROUPS["risky_files"]) == {"backup_database", "mailbox", "executable"}


def test_the_policies_judge_a_folder_once_at_the_last_pass_of_its_scan(monkeypatch) -> None:
    """A folder read in several passes: no verdict on half the files, one run when the scan ends."""
    from types import SimpleNamespace

    from app.api import provisioning_internal as internal
    from app.services import remediations

    runs = []
    monkeypatch.setattr(internal, "_extract_storage_root_id_from_probe", lambda **_kw: 4)
    monkeypatch.setattr(sensitivity, "record_result", lambda *_a: {})
    monkeypatch.setattr(sensitivity, "refresh_exposure", lambda *_a: None)
    monkeypatch.setattr(sensitivity, "flagged_by_root", lambda *_a: {})
    monkeypatch.setattr(remediations, "after_scan", lambda *_a: None)
    monkeypatch.setattr(internal, "_tell_sensitivity_end", lambda *_a, **_kw: None)
    monkeypatch.setattr(policies, "run_all", lambda _db, **kw: runs.append(kw))
    db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    job = SimpleNamespace(action=sensitivity.ACTION, id=9, payload_json=None)

    monkeypatch.setattr(sensitivity, "continue_if_pending", lambda *_a: 10)  # another pass follows
    internal._persist_sensitivity_result(db, job_row=job, result_json={})
    assert runs == []
    monkeypatch.setattr(sensitivity, "continue_if_pending", lambda *_a: None)  # the last pass
    internal._persist_sensitivity_result(db, job_row=job, result_json={})
    assert runs == [{"only_root_ids": {4}, "trigger": "sensitivity_scan", "allow_jobs": False}]


def test_each_folder_says_which_policy_set_or_removed_its_tag(_events) -> None:
    _run({"add_tag": 5, "remove_tag": True}, _Db(hits=[(2,)]))  # folder 1 starts matching, folder 2 stops
    lines = [(e["action"], e["target_id"], e["target_display"], e["context_json"]["policy"], e["context_json"]["tag"]) for e in _events]
    assert lines == [("tag.auto_attached", 1, "Compta", "p", "Mots de passe"), ("tag.auto_detached", 2, "RH", "p", "Mots de passe")]


def test_a_policy_whose_tag_is_gone_fails_instead_of_counting_tags(_events) -> None:
    with pytest.raises(ValueError, match="n'existe plus"):
        _run({"add_tag": 5, "remove_tag": True}, _Db(tag_name=None))
    assert _events == []


class _PolicyDb:
    """Two policies, one sets tag 5."""

    def __init__(self):
        self.sql = []

    def execute(self, statement, params=None):
        text = " ".join(str(statement).split())
        self.sql.append((text, params))
        if text.startswith("SELECT * FROM governance_policies"):
            base = {"description": None, "enabled": 1, "condition_query": "est:sensible", "last_run_at": None, "last_matched": 0, "last_new": 0,
                    "last_error": None, "updated_by": None, "updated_at": None}
            return _Result([{**base, "id": 1, "name": "Secrets", "actions_json": '{"add_tag": 5, "remove_tag": true}'},
                            {**base, "id": 2, "name": "Autre", "actions_json": '{"add_tag": 6}'}])
        return _Result()


def test_a_merged_tag_moves_the_policies_that_set_it() -> None:
    db = _PolicyDb()
    assert policies.using_tag(db, 5) == [{"id": 1, "name": "Secrets"}]
    assert policies.retag(db, 5, 9) == 1
    update = [params for text, params in db.sql if text.startswith("UPDATE governance_policies")]
    assert update == [{"actions": '{"add_tag": 9, "remove_tag": true}', "id": 1}]


def test_a_tag_a_policy_sets_cannot_be_deleted(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.api import tags as tags_api

    monkeypatch.setattr(tags_api, "require_admin", lambda _actor: None)
    monkeypatch.setattr(tags_api, "actor_from_request", lambda _r: None)
    db = _PolicyDb()
    db.get = lambda _model, _id: SimpleNamespace(id=5, name="Mots de passe", color=None)
    with pytest.raises(HTTPException) as refused:
        tags_api.delete_tag(5, SimpleNamespace(headers={}), db)
    assert refused.value.status_code == 409 and refused.value.detail["code"] == "TAG_USED_BY_POLICY" and "Secrets" in refused.value.detail["message"]
