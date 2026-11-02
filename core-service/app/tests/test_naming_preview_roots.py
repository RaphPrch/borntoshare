from __future__ import annotations

from app.api import naming_policies as api


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


class _Db:
    def __init__(self, roots, profiles):
        self.roots, self.profiles = roots, profiles

    def execute(self, statement, params=None):
        sql = str(statement)
        if "storage_root_access_profiles" in sql:
            return _Result(self.profiles)
        rows = self.roots
        if params and params.get("q"):
            needle = params["q"].strip("%").lower()
            rows = [r for r in rows if needle in r["name"].lower() or needle in r["root_path"].lower()]
        return _Result(rows)


def _setup(monkeypatch):
    roots = [{"id": i, "name": f"Dossier {i}", "root_path": f"\\\\FILER01\\Share\\D{i}"} for i in range(1, 8)]
    profiles = [
        {"storage_root_id": 1, "level": "READ", "group_name": "B2S_D1_RX"},
        {"storage_root_id": 2, "level": "READ", "group_name": "GG_OLD_NAME"},
    ]
    monkeypatch.setattr(api, "resolve_storage_root_naming", lambda db, rid, draft_scope=None, draft_template=None: ({"t": draft_template}, "CORP", f"D{rid}"))
    monkeypatch.setattr(api, "resolve_group_name_from_effective_policy",
                        lambda effective_policy, zone_code, storage_root_path, perm: {
                            "samAccountName": f"{'NEW' if effective_policy['t'] else 'B2S'}_{storage_root_path}_{'RX' if perm == 'READ' else 'RW'}"})
    return _Db(roots, profiles)


def test_pages_filter_and_drift(monkeypatch) -> None:
    db = _setup(monkeypatch)
    page = api.preview_root_groups(api.NamingRootsPreviewPayload(zone_id=1, limit=3, offset=3), db)["data"]
    assert page["total"] == 7 and [i["storage_root_id"] for i in page["items"]] == [4, 5, 6]
    assert page["drift_total"] == 1 and page["existing_groups"] == 2

    drift = api.preview_root_groups(api.NamingRootsPreviewPayload(zone_id=1, limit=10, drift_only=True), db)["data"]
    assert [(i["storage_root_id"], i["existing_read_group"], i["drift"]) for i in drift["items"]] == [(2, "GG_OLD_NAME", True)]

    found = api.preview_root_groups(api.NamingRootsPreviewPayload(zone_id=1, query="dossier 1", template="X"), db)["data"]
    # a draft template renames what is shown, the drift stays measured against the saved rule
    assert [(i["read_group"], i["drift"]) for i in found["items"]] == [("NEW_D1_RX", False)]
