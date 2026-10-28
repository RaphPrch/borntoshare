"""AD login through a group that has a role, and dedicated service accounts per capability."""
from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 10):
    pytest.skip("Requires Python >= 3.10 for SQLAlchemy mapped union annotations", allow_module_level=True)

from app.api import internal_identities as router
from app.services import identity_source_accounts as accounts


class _Rows:
    def __init__(self, rows, rowcount: int = 0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _ScriptedDB:
    """Answers each statement from the first rule whose marker is in the SQL."""

    def __init__(self, rules: list[tuple[str, list]]):
        self.rules = rules
        self.calls: list[tuple[str, dict]] = []
        self.committed = False

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split()).lower()
        self.calls.append((sql, dict(params or {})))
        for marker, rows in self.rules:
            if marker in sql:
                return _Rows(rows(self) if callable(rows) else rows)
        return _Rows([])

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def ran(self, marker: str) -> bool:
        return any(marker in sql for sql, _ in self.calls)


ENTITLEMENT = "join identity_roles ir on ir.directory_group_id = dem.directory_group_id"
EXISTING = "from identities i where i.auth_source = 'ad'"
SNAPSHOT_USER = "from directory_snapshot_users"

MARC = {
    "external_id": "CN=Marc,CN=Users,DC=example,DC=test",
    "username": "marc.admin",
    "display_name": "Marc",
    "email": "marc.admin@example.test",
    "is_active": 1,
}


def _resolve(db, **overrides):
    return router.resolve_ad_identity(
        router.ResolveAdIdentityRequest(
            **{"username": "marc.admin", "identity_source_id": 5, "provision_if_entitled": True, **overrides}
        ),
        db=db,
    )


def test_member_of_an_entitled_group_gets_an_identity_at_first_login() -> None:
    db = _ScriptedDB([
        # no identity until the insert
        (EXISTING, lambda db: [{**MARC, "id": 114}] if db.ran("insert into identities") else []),
        (ENTITLEMENT, [(1,)]),
        (SNAPSHOT_USER, [MARC]),
    ])

    out = _resolve(db)

    assert out.found is True
    assert out.identity_id == "114"
    insert = next(params for sql, params in db.calls if sql.startswith("insert into identities"))
    assert insert["provisioning_source"] == "group_entitlement"
    assert db.committed is True


def test_user_without_an_entitled_group_is_not_created() -> None:
    db = _ScriptedDB([(EXISTING, []), (ENTITLEMENT, [])])

    out = _resolve(db)

    assert out.found is False
    assert out.reason_code == "NOT_ENTITLED"
    assert not db.ran("insert into identities")


def test_identity_created_by_a_group_loses_access_when_the_user_leaves_the_groups() -> None:
    db = _ScriptedDB([
        (EXISTING, [{**MARC, "id": 114, "provisioning_source": "group_entitlement"}]),
        (ENTITLEMENT, []),
    ])

    out = _resolve(db)

    assert out.found is False
    assert out.reason_code == "NOT_ENTITLED"


def test_explicitly_imported_identity_keeps_access_without_group() -> None:
    db = _ScriptedDB([
        (EXISTING, [{**MARC, "id": 30, "provisioning_source": "explicit"}]),
        (ENTITLEMENT, []),
    ])

    out = _resolve(db)

    assert out.found is True
    assert out.identity_id == "30"
    assert not db.ran(ENTITLEMENT)


def test_entitlement_honours_inactive_sources_and_disabled_group_import() -> None:
    db = _ScriptedDB([(ENTITLEMENT, [])])

    router._is_entitled_by_group(db, source_id=5, candidates=["Marc.Admin"])

    sql, params = db.calls[0]
    assert "s.is_active = 1" in sql
    assert "not in ('false', '0')" in sql  # JSON_VALUE gives '0' for a JSON false
    assert params["candidates"] == ["marc.admin"]


def test_login_refuses_an_identity_whose_group_entitlement_ended() -> None:
    db = _ScriptedDB([
        ("from identities i left join identity_sources s", [{
            **MARC, "id": 114, "auth_source": "ad", "source_id": 5, "status": "active",
            "type": "user", "provisioning_source": "group_entitlement",
        }]),
        (ENTITLEMENT, []),
    ])

    out = router.resolve_login_identity(
        router.ResolveLoginIdentityRequest(login="marc.admin", username="marc.admin", upn_hint=None),
        db=db,
    )

    assert out.found is False
    assert out.reason_code == "NOT_ENTITLED"


def test_login_only_considers_ad_identities_of_active_auth_enabled_sources() -> None:
    db = _ScriptedDB([])

    router.resolve_login_identity(
        router.ResolveLoginIdentityRequest(login="paul.martin", username="paul.martin", upn_hint=None),
        db=db,
    )

    sql = db.calls[0][0]
    assert "s.is_active = 1 and s.auth_enabled = 1" in sql


def test_directory_login_finds_users_of_auth_enabled_sources_only() -> None:
    db = _ScriptedDB([("from directory_users", [(5,)])])

    out = router.resolve_directory_login(
        router.ResolveDirectoryLoginRequest(username="lucie.user", upn_hint=None, domain_hint="example.test"),
        db=db,
    )

    assert out.found is True
    assert out.identity_source_id == 5
    assert "auth_enabled = 1" in db.calls[0][0]


# --- dedicated service accounts ---------------------------------------------------------


SOURCE = {"bind_dn": "CN=svc-b2s,DC=example,DC=test", "bind_password_ref": "sm://ad/main"}


def test_each_capability_uses_its_own_account_or_the_account_of_the_source() -> None:
    source = {
        **SOURCE,
        "service_accounts": {
            "snapshot": {"bind_dn": "CN=svc-read,DC=example,DC=test", "bind_password_ref": "sm://ad/read"},
            # incomplete account: ignored
            "auth": {"bind_dn": "CN=svc-auth,DC=example,DC=test", "bind_password_ref": ""},
        },
    }

    assert accounts.account_for(source, "snapshot") == ("CN=svc-read,DC=example,DC=test", "sm://ad/read")
    assert accounts.account_for(source, "auth") == (SOURCE["bind_dn"], SOURCE["bind_password_ref"])
    assert accounts.account_for(source, "provisioning") == (SOURCE["bind_dn"], SOURCE["bind_password_ref"])


def test_saving_accounts_keeps_the_stored_password_and_removes_empty_accounts() -> None:
    db = _ScriptedDB([
        ("select purpose, bind_dn, bind_password_ref", [
            {"purpose": "auth", "bind_dn": "CN=old,DC=example,DC=test", "bind_password_ref": "sm://ad/auth"},
        ]),
    ])

    accounts.save_accounts(db, 5, {
        "auth": {"bind_dn": "CN=svc-auth,DC=example,DC=test"},
        "snapshot": None,
        "provisioning": {"bind_dn": "CN=svc-prov,DC=example,DC=test", "bind_password_ref": "sm://ad/prov"},
    })

    writes = [(sql, params) for sql, params in db.calls if not sql.startswith("select")]
    upserts = {params["purpose"]: params for sql, params in writes if sql.startswith("insert")}
    deletes = [params["purpose"] for sql, params in writes if sql.startswith("delete")]
    assert upserts["auth"]["ref"] == "sm://ad/auth"
    assert upserts["provisioning"]["ref"] == "sm://ad/prov"
    assert deletes == ["snapshot"]


def test_a_new_account_needs_a_password() -> None:
    db = _ScriptedDB([])

    with pytest.raises(ValueError):
        accounts.save_accounts(db, 5, {"provisioning": {"bind_dn": "CN=svc-prov,DC=example,DC=test"}})


def test_the_ui_never_receives_the_secret_reference() -> None:
    public = accounts.public_accounts({"auth": {"bind_dn": "CN=svc-auth", "bind_password_ref": "sm://ad/auth"}})

    assert public == {"auth": {"bind_dn": "CN=svc-auth", "has_password": True}}
