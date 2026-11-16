"""Members of a group named in an ACL: found through indexed lookups (no LOWER() on the columns)."""
from app.data.repositories.storage_roots_views_repo import StorageRootsViewsRepo


class _Repo(StorageRootsViewsRepo):
    def __init__(self):
        self.calls = []

    def _rows(self, sql, params, *expanding):
        text = " ".join(sql.split())
        self.calls.append((text, params))
        assert "LOWER(" not in text
        if text.startswith("SELECT dg.id FROM directory_groups dg WHERE dg.dn ="):
            return [{"id": 7}] if params["group_ref"] == "CN=GG_Compta_RW,OU=Groupes,DC=X" else []
        if text.startswith("SELECT dg.id"):
            return []
        if "FROM directory_effective_memberships" in text:
            assert params["ids"] == [7]
            return [{"identity_id": 3, "display_name": "Zoé", "username": "zoe", "email": None, "upn": "zoe@x", "snapshot_id": 2},
                    {"identity_id": 1, "display_name": "Anne", "username": "anne", "email": None, "upn": "anne@x", "snapshot_id": 2}]
        return []


def test_a_group_found_by_its_dn_gives_its_members_sorted() -> None:
    repo = _Repo()
    members = repo._list_group_members_from_effective_memberships(group_ref="CN=GG_Compta_RW,OU=Groupes,DC=X", identity_source_id=4)
    assert [m["display_name"] for m in members] == ["Anne", "Zoé"] and members[0]["snapshot_id"] == 2
    assert all(params.get("identity_source_id") == 4 for _sql, params in repo.calls if "identity_source_id" in params)


def test_an_unknown_group_asks_nothing_more() -> None:
    repo = _Repo()
    assert repo._list_group_members_from_directory_group_members(group_ref="Inconnu", identity_source_id=None) == []
    assert not any("directory_group_members" in sql for sql, _params in repo.calls)
    assert repo._ad_group_exists_for_identity_source(group_ref="Inconnu", identity_source_id=None) is False
