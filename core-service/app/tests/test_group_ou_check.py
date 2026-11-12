from datetime import datetime
from types import SimpleNamespace

from app.services import group_ou_check as g


class FakeDb:
    def __init__(self, check, job):
        self.rows = [check, job]

    def execute(self, *_args, **_kwargs):
        row = self.rows.pop(0)
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: row))

    def rollback(self):
        pass


OU = "OU=CORP,DC=corp,DC=local"
EARLY, LATE = datetime(2026, 11, 11, 19, 0), datetime(2026, 11, 12, 9, 0)


def test_a_refused_creation_blocks_until_a_newer_check_says_delegated():
    failed = {"status": "FAILED", "error_code": "AD_GROUP_CREATE_DENIED", "finished_at": EARLY}
    assert g.verdict(FakeDb(None, failed), 2, OU)["denied"] is True
    ok_check = {"status": "healthy", "message": "", "details_json": '{"code": "OU_DELEGATED"}', "checked_at": LATE}
    assert g.verdict(FakeDb(ok_check, failed), 2, OU)["denied"] is False


def test_the_health_check_alone_says_it_before_any_failure():
    denied = {"status": "down", "message": "", "details_json": '{"code": "OU_NOT_DELEGATED"}', "checked_at": LATE}
    state = g.verdict(FakeDb(denied, None), 2, OU)
    assert state["denied"] and OU in state["message"]
    assert g.verdict(FakeDb({"status": "down", "details_json": '{"code": "OU_CHECK_FAILED"}', "checked_at": LATE, "message": ""}, None), 2, OU)["denied"] is False
    assert g.verdict(None, None, OU)["denied"] is False


def test_the_same_ou_has_one_component_whatever_its_case():
    assert g.component_key(2, OU) == g.component_key(2, OU.lower()) != g.component_key(1, OU)
