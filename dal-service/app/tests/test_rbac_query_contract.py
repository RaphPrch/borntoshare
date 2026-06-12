from __future__ import annotations


def test_rbac_view_sql_contract_is_documented() -> None:
    """Placeholder test.

    This repository is DB-backed and this workspace does not include a test DB harness.
    We keep this test as a minimal guard that the RBAC repo file exists and is importable.
    """

    from app.repositories.identity_roles_repo import IdentityRolesRepo  # noqa: F401

