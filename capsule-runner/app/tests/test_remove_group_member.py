from __future__ import annotations

from types import SimpleNamespace

from app.actions import ad_group_member


def test_a_group_deleted_outside_borntoshare_means_the_member_is_already_gone(monkeypatch) -> None:
    conn = SimpleNamespace(entries=[], search=lambda **_: None, unbind=lambda: None)
    monkeypatch.setattr(ad_group_member.ldap_client, "connect", lambda **_: conn)
    monkeypatch.setattr(ad_group_member.ldap_client, "bind", lambda *_, **__: True)

    ok, message, details = ad_group_member.remove_ad_group_member({
        "host": "dc01.example.test", "bind_dn": "svc", "password": "x", "base_dn": "DC=example,DC=test",
        "group_ref": "B2S_GONE_RX", "principal_dn": "CN=jane,DC=example,DC=test",
    })

    assert ok is True
    assert details["reason"] == "group_not_found"
