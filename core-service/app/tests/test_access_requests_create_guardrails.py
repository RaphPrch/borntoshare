from __future__ import annotations

from fastapi import HTTPException

from app.api import access_requests as api


class _Req:
    def __init__(self) -> None:
        self.headers = {}


class _Repo:
    def __init__(self, db) -> None:
        self.db = db

    def create_with_items(self, *, request_data: dict, items: list[dict]):
        class _Obj:
            id = 123
            code = "REQ-123"

        self.db.last_request_data = dict(request_data)
        self.db.last_items = list(items)
        return _Obj()


class _Db:
    last_request_data: dict | None = None
    last_items: list | None = None


def _payload(permission: str = "read") -> api.AccessRequestCreate:
    return api.AccessRequestCreate(
        requester_identity_id=10,
        storage_root_id=2,
        permissions=[permission],
        justification="test",
        requested_principal={"id": 10, "username": "b2s", "dn": "CN=b2s,OU=CORP,DC=corp,DC=local"},
    )


def test_create_access_request_blocks_when_access_already_granted(monkeypatch) -> None:
    db = _Db()
    monkeypatch.setattr(api, "_find_open_request_for_principal", lambda **kwargs: None)
    monkeypatch.setattr(api, "_current_access_level_for_principal", lambda **kwargs: "READ")
    monkeypatch.setattr(api, "AccessRequestsRepo", _Repo)
    monkeypatch.setattr(api, "log_activity", lambda *args, **kwargs: None)

    try:
        api.create_access_request(_payload("read"), _Req(), db)
        raised = False
    except HTTPException as exc:
        raised = True
        assert exc.status_code == 409
        assert isinstance(exc.detail, dict)
        assert exc.detail.get("code") == "ACCESS_ALREADY_GRANTED"

    assert raised is True


def test_create_access_request_blocks_when_pending_request_exists(monkeypatch) -> None:
    db = _Db()
    monkeypatch.setattr(api, "_find_open_request_for_principal", lambda **kwargs: {"id": 99, "code": "REQ-99"})
    monkeypatch.setattr(api, "_current_access_level_for_principal", lambda **kwargs: "NONE")
    monkeypatch.setattr(api, "AccessRequestsRepo", _Repo)
    monkeypatch.setattr(api, "log_activity", lambda *args, **kwargs: None)

    try:
        api.create_access_request(_payload("write"), _Req(), db)
        raised = False
    except HTTPException as exc:
        raised = True
        assert exc.status_code == 409
        assert isinstance(exc.detail, dict)
        assert exc.detail.get("code") == "ACCESS_REQUEST_ALREADY_EXISTS"

    assert raised is True


def test_create_access_request_allows_write_elevation_from_read(monkeypatch) -> None:
    db = _Db()
    monkeypatch.setattr(api, "_find_open_request_for_principal", lambda **kwargs: None)
    monkeypatch.setattr(api, "_current_access_level_for_principal", lambda **kwargs: "READ")
    monkeypatch.setattr(api, "AccessRequestsRepo", _Repo)
    monkeypatch.setattr(api, "log_activity", lambda *args, **kwargs: None)

    out = api.create_access_request(_payload("write"), _Req(), db)

    assert out.get("data", {}).get("message") == "access_request.created"
    assert db.last_items == [
        {
            "target_type": "storage_root",
            "target_id": 2,
            "permission": "write",
            "expires_at": None,
        }
    ]


class _Rows:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _RowsDb:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def execute(self, *args, **kwargs):
        return _Rows(self.rows)


def test_granted_level_counts_approved_requests_before_the_next_sync() -> None:
    db = _RowsDb(
        [
            # Requested by an administrator (identity 12) for Paul: matched on the login, not on the requester
            {"requester_identity_id": 12, "requested_principal_json": '{"username": "paul.martin", "type": "user"}', "permission": "contribution"},
            {"requester_identity_id": 12, "requested_principal_json": '{"username": "jane.doe", "type": "user"}', "permission": "read"},
        ]
    )
    paul = api._principal_match_keys(identity_id=12, principal_dn=None, principal_username="paul.martin")
    jane = api._principal_match_keys(identity_id=12, principal_dn=None, principal_username="jane.doe")
    other = api._principal_match_keys(identity_id=12, principal_dn=None, principal_username="lucie.user")

    assert api._granted_level_from_requests(db=db, storage_root_id=2, wanted=paul) == "WRITE"
    assert api._granted_level_from_requests(db=db, storage_root_id=2, wanted=jane) == "READ"
    assert api._granted_level_from_requests(db=db, storage_root_id=2, wanted=other) == "NONE"


def test_same_principal_ignores_the_shared_requester_id() -> None:
    # An administrator (identity 12) requests for Claire then Alice: two different people
    claire = api._principal_match_keys(identity_id=12, principal_dn=None, principal_username="claire.auditor")
    alice = api._principal_match_keys(identity_id=12, principal_dn=None, principal_username="alice.finance")
    alice_dn = api._principal_match_keys(identity_id=None, principal_dn=None, principal_username="ALICE.FINANCE")
    self_request = api._principal_match_keys(identity_id=12, principal_dn=None, principal_username=None)

    assert api._same_principal(alice, claire) is False
    assert api._same_principal(alice, alice_dn) is True
    assert api._same_principal(self_request, claire) is True  # no login on one side: the identity decides
