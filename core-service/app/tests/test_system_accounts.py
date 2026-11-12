from app.services import storage_root_permissions as srp


def test_a_renamed_administrator_added_in_the_settings_is_expected(monkeypatch):
    monkeypatch.setitem(srp._broad_cache, "at", 10**12)
    monkeypatch.setitem(srp._broad_cache, "system", frozenset({"sla-prd"}))
    assert srp.is_expected_system_principal("CORP\\sla-prd")
    assert srp.is_expected_system_principal("BUILTIN\\Administrateurs")
    assert not srp.is_expected_system_principal("CORP\\paul.martin")
    assert not srp.is_expected_system_principal("BUILTIN\\Utilisateurs")
