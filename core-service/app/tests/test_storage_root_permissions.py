from __future__ import annotations

import json

from app.services.storage_root_permissions import StorageRootPermissions, inherited_scope, rights_from_raw, short_name


def test_rights_from_raw() -> None:
    assert rights_from_raw("ALLOWED/OI|CI/READ") == "read"
    assert rights_from_raw("ALLOWED/OI|CI/RWXD") == "modify"  # what BornToShare sets for WRITE
    assert rights_from_raw("ALLOWED/0x0/FULL") == "full"
    assert rights_from_raw("ALLOWED/OI|CI/0x001301bf") == "modify"
    assert rights_from_raw("DENIED/OI|CI/READ") == "deny"
    assert rights_from_raw("ALLOWED/0x0/0x00000001") == "special"
    assert inherited_scope("ALLOWED/OI|CI/READ") and not inherited_scope("ALLOWED/0x0/FULL")
    assert short_name("EXAMPLE\\B2S_X_RX") == "b2s_x_rx"


class _Fake(StorageRootPermissions):
    """Same computation, inputs from memory instead of SQL."""

    def __init__(self) -> None:
        super().__init__(db=None)  # type: ignore[arg-type]

    def _root(self, root_id):
        acl = [
            {"principal": "NT AUTHORITY\\SYSTEM", "raw": "ALLOWED/OI|CI/FULL"},
            {"principal": "EXAMPLE\\svc-b2s-files", "raw": "ALLOWED/OI|CI/FULL"},
            {"principal": "EXAMPLE\\B2S_FIN_RX", "raw": "ALLOWED/OI|CI/READ"},
            {"principal": "EXAMPLE\\B2S_FIN_RW", "raw": "ALLOWED/OI|CI/RWXD"},
            {"principal": "EXAMPLE\\GG_Finance", "raw": "ALLOWED/OI|CI/READ"},
            {"principal": "Everyone", "raw": "ALLOWED/0x0/READ"},
        ]
        return {"id": 1, "name": "Finance", "root_path": r"\\fs\corp\finance", "identity_source_id": 7,
                "endpoint_account": "EXAMPLE\\svc-b2s-files",
                "discovered_permissions_json": json.dumps({"discovered_at": "2026-10-29T10:00:00", "permissions": acl})}

    def _all(self, sql, params):
        if "storage_root_access_profiles" in sql:
            return [{"id": 1, "access_level_code": "READ", "group_name": "B2S_FIN_RX", "group_external_id": None, "status": "SUCCEEDED"},
                    {"id": 2, "access_level_code": "WRITE", "group_name": "B2S_FIN_RW", "group_external_id": None, "status": "SUCCEEDED"}]
        return []

    def _requests(self, root_id):
        # Requested by an administrator for Paul: Paul is the beneficiary, not the administrator
        return [{"id": 263, "code": "REQ-263", "decided_at": "2026-10-29T08:20:00", "permission": "read", "level": "read",
                 "expires_at": "2026-11-28T00:00:00", "requester": "preview.admin",
                 "principal": {"type": "user", "username": "paul.martin", "display_name": "Paul Martin"}}]

    def group_members(self, group_name, source_id):
        return {
            "B2S_FIN_RX": [{"username": "paul.martin", "display_name": "Paul Martin", "depth": 0}],
            "B2S_FIN_RW": [{"username": "alice.finance", "display_name": "Alice Finance", "depth": 0}],
            "GG_Finance": [{"username": "bob", "display_name": "Bob", "depth": 0}],
        }.get(group_name, [])

    def _group_info(self, group_name, source_id):
        return {"dn": f"CN={group_name},OU=B2S Groups,DC=example,DC=test"}

    def _snapshot_at(self, source_id):
        return "2026-10-29T09:00:00"

    def _exceptions(self, root_id):
        return {}


def test_build_sorts_acl_and_people() -> None:
    result = _Fake().build(1)

    assert [g["ace"] for g in result["groups"]] == ["ok", "ok"]
    assert {s["name"] for s in result["system"]} == {"SYSTEM", "svc-b2s-files"}
    assert {g["name"]: g["kind"] for g in result["gaps"]} == {"GG_Finance": "outside", "Everyone": "broad"}
    assert result["status"] == "gap"

    people = {p["username"]: p for p in result["people"]}
    assert "preview.admin" not in people  # the requester is not given access
    assert people["paul.martin"]["level"] == "read"
    assert [v["kind"] for v in people["paul.martin"]["via"]] == ["request", "group"]
    assert people["paul.martin"]["expires_at"] == "2026-11-28T00:00:00"
    assert people["alice.finance"]["level"] == "write"
    assert people["alice.finance"]["via"][0]["kind"] == "ad_only"  # in the group without a request
    assert people["bob"]["via"][0]["kind"] == "outside"
    assert result["summary"]["people"] == 3 and result["summary"]["write"] == 1


def test_inheritance_state_reads_the_control_flags():
    from app.services.storage_root_permissions import inheritance_state

    aces = [{"raw": "ALLOWED/OI|CI|I/FULL"}, {"raw": "ALLOWED/OI|CI/READ"}, {"raw": "garbage"}]
    assert inheritance_state("SR|PD|DP", aces) == {"known": True, "broken": True, "inherited_entries": 1}
    assert inheritance_state("SR|DP", aces)["broken"] is False
    assert inheritance_state(None, [])["known"] is False
