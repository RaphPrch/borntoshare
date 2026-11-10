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
