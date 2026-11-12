from ldap3 import ServerPool

from app.shared import ldap_client, winrm


def test_a_directory_host_may_list_several_controllers():
    assert ldap_client.hosts_of("AD01.corp.local, AD02.corp.local;AD03") == ["AD01.corp.local", "AD02.corp.local", "AD03"]
    assert ldap_client.hosts_of("  ") == []
    pool = ldap_client.server_or_pool(host="10.0.0.1, 10.0.0.2", port=636, use_ssl=False, verify_tls=False, timeout=3)
    assert isinstance(pool, ServerPool) and [s.host for s in pool.servers] == ["10.0.0.1", "10.0.0.2"]
    single = ldap_client.server_or_pool(host="10.0.0.1", port=389, use_ssl=False, verify_tls=False, timeout=3)
    assert not isinstance(single, ServerPool) and single.host == "10.0.0.1"


def test_kerberos_gets_every_controller_in_order(monkeypatch):
    monkeypatch.setattr(winrm.name_resolution, "resolve", lambda name: None)
    monkeypatch.setattr(winrm.name_resolution, "_load", lambda: [])
    assert winrm.kdcs_of("CORP.LOCAL", "10.0.0.1, 10.0.0.2")[:2] == ["10.0.0.1", "10.0.0.2"]
