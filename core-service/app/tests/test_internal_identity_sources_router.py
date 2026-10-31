from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 10):
    pytest.skip("Requires Python >= 3.10 for SQLAlchemy mapped union annotations", allow_module_level=True)

from app.api import internal_identity_sources as router


class _FakeIdentitySource:
    def __init__(
        self,
        *,
        row_id: int,
        source_type: str = "ad",
        name: str = "Directory",
        domain_name: str | None = None,
        is_active: bool = True,
        auth_enabled: bool = False,
        auth_priority: int = 100,
    ) -> None:
        self.id = row_id
        self.directory_flavor = "ad"
        self.tls_verify = True
        self.tls_ca_pem = None
        self.tls_server_name = None
        self.user_filter = None
        self.type = source_type
        self.name = name
        self.domain_name = domain_name
        self.external_id = None
        self.protocol = "ldaps"
        self.host = "dc.local"
        self.port = 636
        self.base_dn = "DC=corp,DC=local"
        self.bind_dn = "CN=svc,OU=Users,DC=corp,DC=local"
        self.bind_password_ref = "sm://ad/svc"
        self.capabilities = {"auth": True, "import_groups": True, "snapshot_enabled": True}
        self.is_active = is_active
        self.auth_enabled = auth_enabled
        self.auth_priority = auth_priority


class _FakeQuery:
    def __init__(self, rows: list[_FakeIdentitySource]) -> None:
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)


class _FakeAccountRows:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeDB:
    def __init__(self, rows: list[_FakeIdentitySource], accounts: list[dict] | None = None) -> None:
        self._rows = rows
        self._accounts = accounts or []

    def query(self, _model):
        return _FakeQuery(self._rows)

    def execute(self, *_args, **_kwargs):
        # identity_source_service_accounts
        return _FakeAccountRows(self._accounts)


def test_get_active_identity_source_requires_auth_enabled() -> None:
    db = _FakeDB(
        [
            _FakeIdentitySource(row_id=11, auth_enabled=False),
            _FakeIdentitySource(row_id=10, auth_enabled=False),
        ]
    )

    with pytest.raises(Exception) as exc:
        router.get_active_identity_source(type="ad", db=db)

    assert getattr(exc.value, "status_code", None) == 404


def test_get_active_identity_source_returns_payload_with_explicit_auth_flags() -> None:
    db = _FakeDB(
        [
            _FakeIdentitySource(row_id=20, auth_enabled=True, auth_priority=5),
        ]
    )

    out = router.get_active_identity_source(type="ad", db=db)

    assert out["id"] == 20
    assert out["auth_enabled"] is True
    assert out["auth_priority"] == 5
    assert out["capabilities"]["auth"] is True


def test_resolve_by_domain_ignores_non_auth_enabled_rows() -> None:
    db = _FakeDB(
        [
            _FakeIdentitySource(row_id=31, auth_enabled=False, domain_name="corp.local"),
            _FakeIdentitySource(row_id=32, auth_enabled=True, domain_name="corp.local", auth_priority=1),
        ]
    )

    out = router.resolve_active_identity_source_by_domain(type="ad", domain="corp.local", db=db)

    assert out["id"] == 32
    assert out["auth_enabled"] is True


def test_payload_for_auth_service_carries_the_dedicated_accounts() -> None:
    db = _FakeDB(
        [_FakeIdentitySource(row_id=10, auth_enabled=True)],
        accounts=[{"purpose": "auth", "bind_dn": "CN=svc-auth,DC=example,DC=test", "bind_password_ref": "sm://ad/svc-auth"}],
    )

    out = router.get_active_identity_source(type="ad", db=db)

    assert out["service_accounts"] == {
        "auth": {"bind_dn": "CN=svc-auth,DC=example,DC=test", "bind_password_ref": "sm://ad/svc-auth"}
    }
    # The account of the source stays the fallback of the other capabilities
    assert out["bind_dn"] == "CN=svc,OU=Users,DC=corp,DC=local"
