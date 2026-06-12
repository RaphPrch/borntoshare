from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.actions import directory_snapshot as action


class _Conn:
    def __init__(self) -> None:
        self.entries = []
        self.unbound = False

    def unbind(self) -> None:
        self.unbound = True


class _Entry:
    def __init__(self, dn: str, attrs: dict):
        self.entry_dn = dn
        self.entry_attributes_as_dict = attrs


def test_collect_directory_snapshot_normalizes_member_external_ids(monkeypatch) -> None:
    conn = _Conn()

    user_dn = "CN=User One,OU=Users,DC=corp,DC=local"
    child_group_dn = "CN=Child Group,OU=Groups,DC=corp,DC=local"

    user_entries = [
        _Entry(
            user_dn,
            {
                "distinguishedName": user_dn,
                "objectGUID": "u-guid-1",
                "objectSid": "S-1-5-21-100",
                "userPrincipalName": "user.one@corp.local",
                "sAMAccountName": "user.one",
                "displayName": "User One",
                "mail": "user.one@corp.local",
                "whenChanged": "20260320132942.0Z",
            },
        )
    ]

    group_entries = [
        _Entry(
            "CN=Parent Group,OU=Groups,DC=corp,DC=local",
            {
                "distinguishedName": "CN=Parent Group,OU=Groups,DC=corp,DC=local",
                "objectGUID": "g-guid-parent",
                "cn": "Parent Group",
                "sAMAccountName": "grp.parent",
                "member": child_group_dn,
                "whenChanged": "20260320133000.0Z",
            },
        ),
        _Entry(
            child_group_dn,
            {
                "distinguishedName": child_group_dn,
                "objectGUID": "g-guid-child",
                "cn": "Child Group",
                "sAMAccountName": "grp.child",
                "member": user_dn,
            },
        ),
        _Entry(
            "CN=Unresolved Group,OU=Groups,DC=corp,DC=local",
            {
                "distinguishedName": "CN=Unresolved Group,OU=Groups,DC=corp,DC=local",
                "objectGUID": "g-guid-unresolved",
                "cn": "Unresolved Group",
                "sAMAccountName": "grp.unresolved",
                "member": "CN=Ghost User,OU=Users,DC=corp,DC=local",
            },
        ),
    ]

    def _fake_connect(*, host: str, port: int, use_ssl: bool, verify_tls: bool, timeout: int):
        assert host == "dc01.corp.local"
        assert port == 636
        assert use_ssl is True
        assert verify_tls is False
        assert timeout == 15
        return conn

    def _fake_bind(_conn, *, bind_dn: str, password: str):
        assert bind_dn == "CN=svc,DC=corp,DC=local"
        assert password == "secret"
        return True

    def _fake_search(_conn, *, base_dn: str, search_filter: str, attributes: list[str], limit: int, scope: str = "subtree"):
        assert base_dn == "DC=corp,DC=local"
        assert scope == "subtree"
        assert limit == 5000
        if "objectClass=user" in search_filter:
            _conn.entries = user_entries
        elif "objectClass=group" in search_filter:
            _conn.entries = group_entries
        else:
            _conn.entries = []
        return []

    monkeypatch.setattr(action.ldap_client, "connect", _fake_connect)
    monkeypatch.setattr(action.ldap_client, "bind", _fake_bind)
    monkeypatch.setattr(action.ldap_client, "search", _fake_search)

    ok, message, details = action.collect_directory_snapshot(
        {
            "snapshot_id": 77,
            "identity_source_id": 3,
            "host": "dc01.corp.local",
            "bind_dn": "CN=svc,DC=corp,DC=local",
            "password": "secret",
            "base_dn": "DC=corp,DC=local",
        }
    )

    assert ok is True
    assert message == "Directory snapshot collected"
    assert conn.unbound is True

    payload = details["payload"]
    assert len(payload["users"]) == 1
    assert len(payload["groups"]) == 3
    assert payload["users"][0]["when_changed"] == "2026-03-20T13:29:42Z"
    assert payload["groups"][0]["when_changed"] == "2026-03-20T13:30:00Z"

    memberships = {
        (m["group_external_id"], m["member_external_id"], m["member_type"])
        for m in payload["memberships"]
    }
    assert memberships == {
        ("g-guid-parent", "g-guid-child", "group"),
        ("g-guid-child", "u-guid-1", "user"),
    }
    assert details["counts"]["memberships"] == 2

    # `member_external_id` must contain projected external IDs, not raw DNs.
    assert all("CN=" not in m["member_external_id"] for m in payload["memberships"])
