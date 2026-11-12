from app.services.providers import ad_ldap


def test_the_sign_in_tries_each_controller(monkeypatch):
    monkeypatch.setattr(ad_ldap, "_resolve_bind_password", lambda src, target=None: "x")
    cfg = ad_ldap._build_ad_config({"id": 2, "host": "AD01.corp.local, AD02.corp.local", "protocol": "ldaps", "auth_enabled": True,
                                    "bind_dn": "svc@corp.local", "bind_password_ref": "sm://x", "base_dn": "DC=corp,DC=local"}, target="t")
    assert cfg.urls == ("ldaps://AD01.corp.local:636", "ldaps://AD02.corp.local:636") and cfg.url == cfg.urls[0]
    server = ad_ldap.ADLDAPProvider()._build_server(cfg)
    assert type(server).__name__ == "ServerPool" and len(server.servers) == 2
