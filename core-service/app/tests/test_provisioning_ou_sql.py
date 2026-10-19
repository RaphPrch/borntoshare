from __future__ import annotations

from app.services.provisioning_ou_sql import effective_group_ou_case_sql


def test_effective_group_ou_case_sql_uses_default_group_ou_only() -> None:
    sql = effective_group_ou_case_sql()
    assert "NULLIF(ids.base_dn, '')" not in sql
    assert "NULLIF(ids.default_group_ou_dn, '')" in sql
    assert "NULLIF(se.sub_ou_dn, '')" in sql


def test_effective_group_ou_case_sql_does_not_append_when_sub_ou_contains_dc() -> None:
    sql = effective_group_ou_case_sql()
    assert "INSTR(UPPER(se.sub_ou_dn), 'DC=') = 0" in sql
