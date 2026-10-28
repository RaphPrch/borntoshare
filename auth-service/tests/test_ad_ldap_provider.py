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

    monkeypatch.setattr(module.settings, "AD_ENABLED", True)
    monkeypatch.setattr(module, "Connection", object())
    monkeypatch.setattr(module, "Server", object())

    async def _fake_load(_domain_hint):
        return module.ADConfig(
            source_id=7,
            url="ldaps://dc01.corp.local:636",
            base_dn="DC=corp,DC=local",
            user_filter="(sAMAccountName={username})",
            bind_user="CN=svc,OU=Users,DC=corp,DC=local",
            bind_password="secret",
            user_dn_template="",
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
    monkeypatch.setattr(module.settings, "AD_ENABLED", True)
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
        user_filter="(sAMAccountName={username})",
        bind_user="CN=svc,OU=Users,DC=corp,DC=local",
        bind_password="secret",
        user_dn_template="",
    )

    with pytest.raises(InvalidCredentials):
        provider._authenticate_blocking(cfg, "alice@corp.local", "secret")

    assert search_calls == [("alice@corp.local", "alice")]


def test_authenticate_for_source_uses_resolved_source(monkeypatch) -> None:
    from app.services.providers import ad_ldap as module

    provider = module.ADLDAPProvider()
    monkeypatch.setattr(module.settings, "AD_ENABLED", True)
    monkeypatch.setattr(module, "Connection", object())
    monkeypatch.setattr(module, "Server", object())

    async def _fake_load(source_id):
        assert source_id == 2
        return module.ADConfig(
            source_id=2,
            url="ldap://192.168.100.40:389",
            base_dn="DC=corp,DC=local",
            user_filter="(sAMAccountName={username})",
            bind_user="CORP\\Administrator",
            bind_password="secret",
            user_dn_template="",
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

    monkeypatch.setattr(module.settings, "AD_USER_FILTER", "(sAMAccountName={username})", raising=False)
    monkeypatch.setattr(module.settings, "AD_USER_DN_TEMPLATE", "", raising=False)
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


def test_tls_verification_requires_the_ca_file(monkeypatch, tmp_path) -> None:
    import ssl

    from app.services.providers import ad_ldap as module
    from app.services.providers.base import ProviderMisconfigured

    monkeypatch.setattr(module.settings, "LDAP_TLS_VERIFY", False)
    assert module._tls_config() is None

    monkeypatch.setattr(module.settings, "LDAP_TLS_VERIFY", True)
    monkeypatch.setattr(module.settings, "LDAP_CA_FILE", str(tmp_path / "missing.pem"))
    with pytest.raises(ProviderMisconfigured):
        module._tls_config()

    ca = tmp_path / "ad-ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n")
    monkeypatch.setattr(module.settings, "LDAP_CA_FILE", str(ca))
    tls = module._tls_config()
    assert tls.validate == ssl.CERT_REQUIRED
    assert tls.ca_certs_file == str(ca)
