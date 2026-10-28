from __future__ import annotations

import json

from app.services import sso_service

PROVIDER = {
    "id": 2, "identity_source_id": 9, "is_enabled": 1, "link_existing_identities": 1, "default_role": None,
    "role_mapping_json": json.dumps([{"value": "b2s-admins", "role": "platform_admin"}, {"value": "/b2s-users", "role": "user"}]),
}


class _Rows:
    def __init__(self, rows, lastrowid=None):
        self._rows, self.lastrowid = rows, lastrowid

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _DB:
    def __init__(self, *, existing=None, ad=None, provider=PROVIDER):
        self.existing, self.ad, self.provider = existing, ad, provider
        self.calls: list[tuple[str, dict]] = []

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split()).lower()
        self.calls.append((sql, dict(params or {})))
        if "from sso_providers" in sql:
            return _Rows([self.provider] if self.provider else [])
        if "where source_id = :sid and external_id = :sub" in sql:
            return _Rows([self.existing] if self.existing else [])
        if "lower(i.auth_source) = 'ad'" in sql:
            return _Rows([self.ad] if self.ad else [])
        if sql.startswith("insert into identities"):
            return _Rows([], lastrowid=55)
        if "select id, code from roles" in sql:
            return _Rows([{"id": 1, "code": "user"}, {"id": 2, "code": "platform_admin"}])
        return _Rows([])

    def ran(self, marker):
        return [p for s, p in self.calls if marker in s]


CLAIMS = {"sub": "kc-1", "username": "alice", "email": "alice@example.com", "name": "Alice", "roles": ["b2s-admins"]}


def test_mapping_is_case_insensitive_and_ignores_the_group_slash() -> None:
    assert sso_service.mapped_roles(PROVIDER, ["B2S-ADMINS"]) == ["platform_admin"]
    assert sso_service.mapped_roles(PROVIDER, ["b2s-users"]) == ["user"]
    assert sso_service.mapped_roles(PROVIDER, ["other"]) == []
    assert sso_service.mapped_roles({**PROVIDER, "default_role": "user"}, ["other"]) == ["user"]


def test_first_sign_in_with_a_mapped_role_creates_the_identity_with_sso_roles() -> None:
    db = _DB()
    out = sso_service.resolve_sso_identity(db, provider_id=2, claims=CLAIMS)
    assert out == {"found": True, "identity_id": 55, "is_active": True, "linked": "created", "roles": ["platform_admin"]}
    insert = db.ran("insert into identities")[0]
    assert insert["sid"] == 9 and insert["sub"] == "kc-1"
    assert db.ran("insert into identity_roles")[0]["role_id"] == 2


def test_an_imported_directory_account_with_the_same_name_is_used() -> None:
    db = _DB(ad={"id": 40, "is_active": 1})
    out = sso_service.resolve_sso_identity(db, provider_id=2, claims={**CLAIMS, "roles": []})
    assert out["identity_id"] == 40 and out["linked"] == "ad"
    assert not db.ran("insert into identities")


def test_no_mapped_role_and_no_account_refuses() -> None:
    out = sso_service.resolve_sso_identity(_DB(), provider_id=2, claims={**CLAIMS, "roles": ["other"]})
    assert out == {"found": False, "reason_code": "NOT_ENTITLED"}


def test_an_sso_identity_loses_access_when_its_role_is_removed_in_keycloak() -> None:
    db = _DB(existing={"id": 55, "is_active": 1, "status": "active"})
    out = sso_service.resolve_sso_identity(db, provider_id=2, claims={**CLAIMS, "roles": []})
    assert out["reason_code"] == "NOT_ENTITLED"


def test_sso_roles_are_replaced_without_touching_manual_roles() -> None:
    db = _DB(existing={"id": 55, "is_active": 1, "status": "active"})
    sso_service.resolve_sso_identity(db, provider_id=2, claims=CLAIMS)
    deleted = [s for s, _ in db.calls if s.startswith("delete from identity_roles")]
    assert deleted and "source = 'sso'" in deleted[0]


def test_a_disabled_provider_refuses() -> None:
    out = sso_service.resolve_sso_identity(_DB(provider={**PROVIDER, "is_enabled": 0}), provider_id=2, claims=CLAIMS)
    assert out["reason_code"] == "PROVIDER_DISABLED"
