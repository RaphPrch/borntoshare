from app.services import policies, sensitivity


class _Result:
    def __init__(self, rows=None, rowcount=0):
        self.rows, self.rowcount = rows or [], rowcount

    def all(self):
        return self.rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class _Db:
    """Hits of the policy before the run: folders 1 and 2; the run sees only folder 1 matching."""

    def __init__(self):
        self.sql = []

    def execute(self, statement, params=None):
        text = " ".join(str(statement).split())
        self.sql.append((text, params))
        if text.startswith("SELECT storage_root_id FROM governance_policy_hits"):
            return _Result([(1,), (2,)])
        if text.startswith("DELETE FROM storage_root_tags"):
            return _Result(rowcount=len(params["ids"]))
        return _Result()

    def commit(self):
        pass


def _run(actions):
    db = _Db()
    rows = [{"storage_root_id": 1, "password_files": 1}, {"storage_root_id": 2, "password_files": 0}]
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
