from __future__ import annotations

from app.actions import infra_health, ldap_test


def _target(**extra):
    return {
        "component": "identity_source:7", "kind": "ldap", "target": "adlab.example.test:636", "use_ssl": True,
        "base_dn": "DC=example,DC=test", "bind_dn": "svc-b2s-read@example.test", "secret_ref": "sm://ref", **extra,
    }


def test_directory_is_checked_with_a_real_bind(monkeypatch) -> None:
    seen: dict = {}

    def fake_bind(params):
        seen.update(params)
        return True, "ok", {"duration_ms": 12, "use_ssl": True, "tls_verified": True}

    monkeypatch.setattr(ldap_test, "test_ldap_bind", fake_bind)
    monkeypatch.setattr(infra_health, "_ldap_passwords", lambda targets: {"sm://ref": "secret"})

    ok, _message, details = infra_health.run_infra_health_check({"targets": [_target()]})

    result = details["results"][0]
    assert ok is True
    assert result["status"] == "healthy"
    assert "certificate checked" in result["message"]
    assert seen["host"] == "adlab.example.test" and seen["port"] == 636 and seen["password"] == "secret"


def test_refused_account_puts_the_directory_down(monkeypatch) -> None:
    monkeypatch.setattr(
        ldap_test, "test_ldap_bind",
        lambda params: (False, "bind", {"failure_code": "LDAP_PASSWORD_EXPIRED", "hint": "The password of the service account has expired."}),
    )
    monkeypatch.setattr(infra_health, "_ldap_passwords", lambda targets: {"sm://ref": "secret"})

    _ok, _message, details = infra_health.run_infra_health_check({"targets": [_target()]})

    result = details["results"][0]
    assert result["status"] == "down"
    assert result["message"] == "The password of the service account has expired."
    assert details["down"] == ["identity_source:7"]


def test_unreadable_secret_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(infra_health, "_ldap_passwords", lambda targets: {})

    _ok, _message, details = infra_health.run_infra_health_check({"targets": [_target()]})

    assert details["results"][0]["status"] == "down"
    assert "could not be read" in details["results"][0]["message"]


def test_job_contract_keeps_the_ldap_fields() -> None:
    from app.schemas.actions import InfraHealthPayload

    payload = InfraHealthPayload.model_validate({"targets": [_target()]})
    target = payload.model_dump()["targets"][0]
    assert target["kind"] == "ldap"
    assert target["bind_dn"] == "svc-b2s-read@example.test" and target["secret_ref"] == "sm://ref"


def test_one_unreadable_secret_does_not_hide_the_others(monkeypatch) -> None:
    from app.services import secret_client

    def resolve(refs):
        if refs == ["sm://bad"]:
            raise RuntimeError("Secret prefix not allowed")
        return {ref: "pw" for ref in refs}

    monkeypatch.setattr(secret_client, "resolve_secret_refs", resolve)

    passwords = infra_health._ldap_passwords([_target(secret_ref="sm://bad"), _target()])

    assert passwords == {"sm://ref": "pw"}
