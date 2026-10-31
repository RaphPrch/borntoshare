from __future__ import annotations

import asyncio

import pytest

from app.schemas.auth import UserInfo
from app.services.providers.base import InvalidCredentials


def test_build_search_filters_prefers_sam_and_upn_for_upn_login() -> None:
    from app.services.providers.ad_ldap import _build_search_filters

    out = _build_search_filters(username="alice", raw_username="alice@corp.local")

    assert out == [
        "(sAMAccountName=alice)",
        "(userPrincipalName=alice@corp.local)",
    ]


def test_ad_account_disabled_detects_uac_flag() -> None:
    from app.services.providers.ad_ldap import _ad_account_disabled

    assert _ad_account_disabled(user_account_control=514, computed_control=None) is True
    assert _ad_account_disabled(user_account_control=512, computed_control=None) is False


def test_authenticate_propagates_identity_source_id(monkeypatch) -> None:
    from app.services.providers import ad_ldap as module

    provider = module.ADLDAPProvider()

    monkeypatch.setattr(module, "Connection", object())
    monkeypatch.setattr(module, "Server", object())

    async def _fake_load(_domain_hint):
        return module.ADConfig(
            source_id=7,
            url="ldaps://dc01.corp.local:636",
            base_dn="DC=corp,DC=local",
            user_filter="",
            bind_user="CN=svc,OU=Users,DC=corp,DC=local",
            bind_password="secret",
            directory_flavor="ad",
            tls_verify=False,
            tls_ca_pem=None,
            tls_server_name=None,
        )

    monkeypatch.setattr(module, "_load_active_config_for_domain", _fake_load)
    monkeypatch.setattr(
        provider,
        "_authenticate_sync",
        lambda *_args, **_kwargs: asyncio.sleep(0, result=UserInfo(
            identity_id=None,
            identity_source_id=7,
            username="alice",
            display_name="Alice",
            email="alice@corp.local",
            external_id="guid-1",
            auth_source="ad",
        )),
    )

    out = asyncio.run(provider.authenticate("alice@corp.local", "secret"))
    assert out.identity_source_id == 7


def test_authenticate_blocking_uses_upn_fallback_and_rejects_disabled(monkeypatch) -> None:
    from app.services.providers import ad_ldap as module

    provider = module.ADLDAPProvider()
    monkeypatch.setattr(provider, "_build_server", lambda _cfg: object())

    search_calls: list[tuple[str, str]] = []

    def _fake_search(cfg, server, raw_username, normalized_user):
        search_calls.append((raw_username, normalized_user))
        return module._ADSearchResult(
            user_dn="CN=Alice,OU=Users,DC=corp,DC=local",
            display_name="Alice",
            email="alice@corp.local",
            upn="alice@corp.local",
            object_guid="guid-1",
            object_sid=None,
            disabled=True,
        )

    monkeypatch.setattr(provider, "_search_user", _fake_search)

    cfg = module.ADConfig(
        source_id=9,
        url="ldaps://dc01.corp.local:636",
        base_dn="DC=corp,DC=local",
        user_filter="",
        bind_user="CN=svc,OU=Users,DC=corp,DC=local",
        bind_password="secret",
        directory_flavor="ad",
        tls_verify=False,
        tls_ca_pem=None,
        tls_server_name=None,
    )

    with pytest.raises(InvalidCredentials):
        provider._authenticate_blocking(cfg, "alice@corp.local", "secret")

    assert search_calls == [("alice@corp.local", "alice")]


def test_authenticate_for_source_uses_resolved_source(monkeypatch) -> None:
    from app.services.providers import ad_ldap as module

    provider = module.ADLDAPProvider()
    monkeypatch.setattr(module, "Connection", object())
    monkeypatch.setattr(module, "Server", object())

    async def _fake_load(source_id):
        assert source_id == 2
        return module.ADConfig(
            source_id=2,
            url="ldap://192.168.100.40:389",
            base_dn="DC=corp,DC=local",
            user_filter="",
            bind_user="CORP\\Administrator",
            bind_password="secret",
            directory_flavor="ad",
            tls_verify=False,
            tls_ca_pem=None,
            tls_server_name=None,
        )

    monkeypatch.setattr(module, "_load_active_config_for_source", _fake_load)
    monkeypatch.setattr(
        provider,
        "_authenticate_sync",
        lambda *_args, **_kwargs: asyncio.sleep(0, result=UserInfo(
            identity_id=None,
            identity_source_id=2,
            username="b2s",
            display_name="b2s",
            email=None,
            external_id="guid-1",
            auth_source="ad",
        )),
    )

    out = asyncio.run(provider.authenticate_for_source(source_id=2, username="b2s", password="secret"))
    assert out.identity_source_id == 2


def test_build_ad_config_accepts_ldap_when_identity_source_declares_it(monkeypatch) -> None:
    from app.services.providers import ad_ldap as module

    monkeypatch.setattr(module, "_resolve_bind_password", lambda _src, target=None: "secret")

    cfg = module._build_ad_config(
        {
            "id": 2,
            "protocol": "ldap",
            "host": "192.168.100.40",
            "port": 389,
            "base_dn": "DC=corp,DC=local",
            "bind_dn": "CORP\\Administrator",
            "auth_enabled": True,
        },
        target="2",
    )

    assert cfg.url == "ldap://192.168.100.40:389"


def _source(**overrides) -> dict:
    return {
        "id": 5,
        "protocol": "ldaps",
        "host": "dc01.example.test",
        "port": 636,
        "base_dn": "DC=example,DC=test",
        "bind_dn": "CN=svc-b2s,DC=example,DC=test",
        "bind_password_ref": "sm://ad/main",
        "auth_enabled": True,
        **overrides,
    }


def test_build_ad_config_uses_the_dedicated_auth_account(monkeypatch) -> None:
    from app.services.providers import ad_ldap as module

    resolved: list[str] = []
    monkeypatch.setattr(module, "_resolve_bind_password", lambda src, target=None: resolved.append(src["bind_password_ref"]) or "pw")

    cfg = module._build_ad_config(
        _source(service_accounts={"auth": {"bind_dn": "CN=svc-auth,DC=example,DC=test", "bind_password_ref": "sm://ad/auth"}}),
        target=None,
    )

    assert cfg.bind_user == "CN=svc-auth,DC=example,DC=test"
    assert resolved == ["sm://ad/auth"]


def test_build_ad_config_falls_back_to_the_source_account(monkeypatch) -> None:
    from app.services.providers import ad_ldap as module

    resolved: list[str] = []
    monkeypatch.setattr(module, "_resolve_bind_password", lambda src, target=None: resolved.append(src["bind_password_ref"]) or "pw")

    # Incomplete dedicated account: never mix its DN with the password of another account
    cfg = module._build_ad_config(
        _source(service_accounts={"auth": {"bind_dn": "CN=svc-auth,DC=example,DC=test"}, "snapshot": {"bind_dn": "x", "bind_password_ref": "y"}}),
        target=None,
    )

    assert cfg.bind_user == "CN=svc-b2s,DC=example,DC=test"
    assert resolved == ["sm://ad/main"]


def test_a_refused_user_bind_is_invalid_credentials(monkeypatch) -> None:
    from ldap3.core.exceptions import LDAPBindError

    from app.services.providers import ad_ldap as module

    def _refuse(*_args, **_kwargs):
        raise LDAPBindError("invalidCredentials")

    monkeypatch.setattr(module, "Connection", _refuse)

    with pytest.raises(InvalidCredentials):
        module.ADLDAPProvider._bind_user(object(), "CN=Paul,DC=example,DC=test", "wrong")


def _tls_cfg(module, **overrides):
    values = {"source_id": 1, "url": "ldaps://dc", "base_dn": "DC=x", "user_filter": "", "bind_user": "u",
              "bind_password": "p", "directory_flavor": "ad", "tls_verify": True, "tls_ca_pem": None, "tls_server_name": None}
    return module.ADConfig(**{**values, **overrides})


def test_tls_check_follows_the_settings_of_the_directory() -> None:
    import ssl

    from app.services.providers import ad_ldap as module

    assert module._tls_config(_tls_cfg(module, tls_verify=False)) is None

    tls = module._tls_config(_tls_cfg(module, tls_server_name="dc01.example.test"))
    assert tls.validate == ssl.CERT_REQUIRED
    assert tls.valid_names == ["dc01.example.test"]


def test_build_ad_config_reads_the_user_filter_of_the_directory(monkeypatch) -> None:
    from app.services.providers import ad_ldap as module

    monkeypatch.setattr(module, "_resolve_bind_password", lambda _src, target=None: "secret")
    src = {"id": 2, "protocol": "ldap", "host": "dc", "port": 389, "base_dn": "DC=x", "bind_dn": "u", "bind_password_ref": "sm://x", "auth_enabled": True}

    assert module._build_ad_config(src, target=None).user_filter == ""
    assert module._build_ad_config({**src, "user_filter": "(mail={username})"}, target=None).user_filter == "(mail={username})"


def test_user_filters_follow_the_directory() -> None:
    from app.services.providers import ad_ldap as module

    ad = _tls_cfg(module)
    assert module._user_filters(ad, "jane", "jane") == ["(sAMAccountName=jane)"]
    openldap = _tls_cfg(module, directory_flavor="openldap")
    assert "(uid=jane)" in module._user_filters(openldap, "jane", "jane")[0]
    custom = _tls_cfg(module, user_filter="(mail={username})")
    assert module._user_filters(custom, "j*", "j*") == ["(mail=j\\2a)"]


def test_a_connection_refused_by_the_directory_is_not_a_wrong_password(monkeypatch) -> None:
    from ldap3.core.exceptions import LDAPSocketOpenError, LDAPStrongerAuthRequiredResult

    from app.services.providers import ad_ldap as module
    from app.services.providers.base import AuthUnavailable, ProviderMisconfigured

    def refused(*_a, **_k):
        raise LDAPStrongerAuthRequiredResult("strongerAuthRequired")

    monkeypatch.setattr(module, "Connection", refused)
    with pytest.raises(ProviderMisconfigured):
        module.ADLDAPProvider._bind_user(object(), "CN=Paul,DC=example,DC=test", "secret")

    def down(*_a, **_k):
        raise LDAPSocketOpenError("no route")

    monkeypatch.setattr(module, "Connection", down)
    with pytest.raises(AuthUnavailable):
        module.ADLDAPProvider._bind_user(object(), "CN=Paul,DC=example,DC=test", "secret")
