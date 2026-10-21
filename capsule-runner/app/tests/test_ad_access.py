from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

import pytest
from ldap3 import BASE, MODIFY_ADD
from ldap3.core.exceptions import LDAPSocketOpenError

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.actions import ad_access
from app.core import action_registry as registry
from app.shared import ldap_client

OU = "OU=Groups,DC=example,DC=com"
BASE_DN = "DC=example,DC=com"
JANE = "CN=Jane,OU=Users,DC=example,DC=com"


class _Entry:
    def __init__(self, dn: str, attrs: dict) -> None:
        self.entry_dn = dn
        self.entry_attributes_as_dict = {k: (v if isinstance(v, list) else [v]) for k, v in attrs.items()}


class FakeDirectory:
    """Just enough of an LDAP server for the filters used by grant_ad_access."""

    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}
        self.added: list[str] = []
        self.add(BASE_DN, ["domain"])
        self.add(OU, ["organizationalUnit"])
        self.add(JANE, ["user"], sAMAccountName="jane")

    def add(self, dn: str, classes: list[str], **attrs) -> dict:
        entry = {"objectClass": classes, "distinguishedName": dn, "objectGUID": uuid.uuid4().bytes_le, **attrs}
        self.objects[dn.lower()] = entry
        return entry

    def group(self, dn: str, sam: str, members: list[str] | None = None) -> dict:
        return self.add(dn, ["group"], sAMAccountName=sam, member=list(members or []))

    def connection(self) -> "FakeConn":
        return FakeConn(self)


class FakeConn:
    def __init__(self, directory: FakeDirectory) -> None:
        self.dir = directory
        self.entries: list[_Entry] = []
        self.result: dict = {}

    @staticmethod
    def _matches(entry: dict, search_filter: str) -> bool:
        classes = {c.lower() for c in entry["objectClass"]}
        wanted = re.findall(r"\(objectClass=([^)*]+)\)", search_filter)
        if wanted:
            any_of = "(|(objectClass=" in search_filter
            hits = [w.lower() in classes for w in wanted]
            if not (any(hits) if any_of else all(hits)):
                return False
        pairs = [(a, v) for a, v in re.findall(r"\((\w+)=([^()]*)\)", search_filter) if a != "objectClass"]
        if not pairs:
            return True
        for attr, value in pairs:
            if attr == "objectGUID":
                if "".join(f"\\{b:02x}" for b in entry["objectGUID"]) == value:
                    return True
            elif str(entry.get(attr, "")).lower() == value.replace("\\2a", "*").lower():
                return True
        return False

    def search(self, search_base, search_filter, search_scope=None, attributes=None, size_limit=0):
        base = search_base.lower()
        if search_scope == BASE:
            candidates = [self.dir.objects[base]] if base in self.dir.objects else []
        else:
            candidates = [e for dn, e in self.dir.objects.items() if dn.endswith(base)]
        self.entries = [_Entry(e["distinguishedName"], e) for e in candidates if self._matches(e, search_filter)]
        return bool(self.entries)

    def add(self, dn, classes, attributes):
        if dn.lower() in self.dir.objects:
            self.result = {"description": "entryAlreadyExists"}
            return False
        self.dir.add(dn, classes, **{**attributes, "member": []})
        self.dir.added.append(dn)
        return True

    def modify(self, dn, changes):
        (operation, values), = changes["member"]
        assert operation == MODIFY_ADD
        self.dir.objects[dn.lower()]["member"].extend(values)
        return True

    def unbind(self):
        return True


@pytest.fixture()
def directory(monkeypatch) -> FakeDirectory:
    directory = FakeDirectory()
    monkeypatch.setattr(ldap_client, "connect", lambda **kw: directory.connection())
    monkeypatch.setattr(ldap_client, "bind", lambda conn, **kw: True)
    return directory


def _params(**overrides) -> dict:
    return {
        "host": "dc01.example.com",
        "bind_dn": "CN=svc,DC=example,DC=com",
        "password": "secret",
        "base_dn": BASE_DN,
        "target_ou_dn": OU,
        "group_name": "B2S_FIN_RW",
        "principal_username": "jane",
        **overrides,
    }


def test_first_permission_creates_the_global_group_in_the_zone_ou_and_adds_the_member(directory) -> None:
    ok, _message, details = ad_access.grant_ad_access(_params())

    assert ok is True
    assert details["group_outcome"] == "created"
    assert details["member_outcome"] == "added"
    assert directory.added == [f"CN=B2S_FIN_RW,{OU}"]
    group = directory.objects[f"cn=b2s_fin_rw,{OU}".lower()]
    assert group["groupType"] == -2147483646  # global security group
    assert group["info"] == "Managed by BornToShare"
    assert group["member"] == [JANE]
    assert details["group_guid"]
    assert [step["step"] for step in details["steps"]] == ["connect", "group", "member"]


def test_next_permissions_reuse_the_group_by_guid(directory) -> None:
    _ok, _msg, first = ad_access.grant_ad_access(_params())
    directory.add("CN=Paul,OU=Users,DC=example,DC=com", ["user"], sAMAccountName="paul")

    ok, _message, details = ad_access.grant_ad_access(
        _params(principal_username="paul", group_external_id=first["group_guid"])
    )

    assert ok is True
    assert details["group_outcome"] == "reused"
    assert len(directory.added) == 1
    assert details["member_outcome"] == "added"


def test_already_member_is_not_an_error(directory) -> None:
    directory.group(f"CN=B2S_FIN_RW,{OU}", "B2S_FIN_RW", members=[JANE])

    ok, _message, details = ad_access.grant_ad_access(_params())

    assert ok is True
    assert details["group_outcome"] == "reused"
    assert details["member_outcome"] == "already_member"
    assert directory.added == []


def test_a_group_with_the_same_name_outside_the_ou_is_a_conflict(directory) -> None:
    directory.group("CN=B2S_FIN_RW,OU=Legacy,DC=example,DC=com", "B2S_FIN_RW")

    ok, _message, details = ad_access.grant_ad_access(_params())

    assert ok is False
    assert details["failure_code"] == "AD_GROUP_NAME_CONFLICT"
    assert details["existing_dn"] == "CN=B2S_FIN_RW,OU=Legacy,DC=example,DC=com"
    assert details["retryable"] is False
    assert directory.added == []


def test_an_adopted_group_is_used_even_outside_the_ou(directory) -> None:
    legacy = "CN=B2S_FIN_RW,OU=Legacy,DC=example,DC=com"
    directory.group(legacy, "B2S_FIN_RW")

    ok, _message, details = ad_access.grant_ad_access(_params(adopt_group_dn=legacy))

    assert ok is True
    assert details["group_outcome"] == "adopted"
    assert details["group_dn"] == legacy
    assert directory.objects[legacy.lower()]["member"] == [JANE]


def test_a_group_deleted_from_ad_is_recreated(directory) -> None:
    ok, _message, details = ad_access.grant_ad_access(_params(group_external_id=str(uuid.uuid4())))

    assert ok is True
    assert details["group_outcome"] == "recreated"
    assert details["steps"][1]["status"] == "warning"


def test_missing_ou_and_unknown_requester_fail_without_retry(directory) -> None:
    ok, _message, details = ad_access.grant_ad_access(_params(target_ou_dn="OU=Nowhere,DC=example,DC=com"))
    assert ok is False
    assert details["failure_code"] == "AD_TARGET_OU_NOT_FOUND"

    ok, _message, details = ad_access.grant_ad_access(_params(principal_username="ghost"))
    assert ok is False
    assert details["failure_code"] == "AD_PRINCIPAL_NOT_FOUND"


@pytest.mark.parametrize("name", ["B2S/FIN", "X" * 65, "B2S,FIN"])
def test_invalid_group_names_are_rejected_before_any_ldap_call(monkeypatch, name) -> None:
    monkeypatch.setattr(ldap_client, "connect", lambda **kw: pytest.fail("no LDAP call expected"))

    ok, _message, details = ad_access.grant_ad_access(_params(group_name=name))

    assert ok is False
    assert details["failure_code"] == "AD_GROUP_NAME_INVALID"


def test_unreachable_directory_is_retryable(monkeypatch) -> None:
    def _down(**kw):
        raise LDAPSocketOpenError("connection refused")

    monkeypatch.setattr(ldap_client, "connect", _down)

    ok, _message, details = ad_access.grant_ad_access(_params())

    assert ok is False
    assert details["failure_code"] == "AD_UNREACHABLE"
    assert details["retryable"] is True


def test_a_refused_certificate_is_not_retried(monkeypatch) -> None:
    def _bad_certificate(**kw):
        raise LDAPSocketOpenError("socket ssl wrapping error: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    monkeypatch.setattr(ldap_client, "connect", _bad_certificate)

    ok, _message, details = ad_access.grant_ad_access(_params())

    assert ok is False
    assert details["failure_code"] == "AD_TLS_FAILED"
    assert details["retryable"] is False


def test_registry_retries_only_what_the_action_marks_retryable(monkeypatch) -> None:
    monkeypatch.setattr(registry, "resolve_secret_fields", lambda payload, fields: {**payload, "password": "secret"})
    for retryable, code in ((True, "AD_UNREACHABLE"), (False, "AD_GROUP_NAME_CONFLICT")):
        monkeypatch.setitem(
            registry.ALLOWED_ACTIONS,
            "grant_ad_access",
            registry.ActionSpec(
                action="grant_ad_access",
                schema=registry.ADAccessGrantPayload,
                runner=lambda payload, c=code, r=retryable: (False, "failed", {"failure_code": c, "retryable": r}),
                secret_fields=("secret_ref",),
                target_field="group_name",
            ),
        )
        with pytest.raises(registry.CapsuleActionError) as exc:
            registry.execute_action("grant_ad_access", _params(secret_ref="sm://ad/svc"), job_id=1)
        assert exc.value.error_code == code
        assert exc.value.retryable is retryable
