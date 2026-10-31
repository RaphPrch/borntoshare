from __future__ import annotations

from app.shared import ldap_dialect


def test_the_flavor_of_the_job_chooses_the_dialect() -> None:
    assert ldap_dialect.of({}) is ldap_dialect.ACTIVE_DIRECTORY
    assert ldap_dialect.of({"directory_flavor": "ad"}) is ldap_dialect.ACTIVE_DIRECTORY
    assert ldap_dialect.of({"directory_flavor": "OpenLDAP"}) is ldap_dialect.OPENLDAP


def test_openldap_groups_hold_their_own_place() -> None:
    classes, attrs = ldap_dialect.OPENLDAP.new_group(group_dn="cn=g,ou=x", group_name="g", description="", marker="m")
    assert "groupOfNames" in classes
    assert attrs["member"] == ["cn=g,ou=x"]
    assert "sAMAccountName" not in attrs


def test_active_directory_groups_stay_global_security() -> None:
    classes, attrs = ldap_dialect.ACTIVE_DIRECTORY.new_group(group_dn="CN=g,OU=x", group_name="g", description="", marker="m")
    assert classes == ["top", "group"]
    assert attrs["groupType"] == -2147483646


def test_filters_escape_the_values() -> None:
    assert "(uid=a\\2a)" in ldap_dialect.OPENLDAP.user_ref_filter("a*")
    assert "sAMAccountName=a\\28" in ldap_dialect.ACTIVE_DIRECTORY.group_ref_filter("a(")
