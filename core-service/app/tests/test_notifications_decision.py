"""E-mail of a decision: the requester and the person the access is for (a request may be made for someone else)."""

from __future__ import annotations

from app.services import notifications


def test_a_request_for_someone_else_reaches_both() -> None:
    row = {"requester_email": "manager@corp.local", "beneficiary_email": "paul.martin@corp.local"}
    assert notifications.decision_recipients(row) == ["manager@corp.local", "paul.martin@corp.local"]


def test_a_request_for_oneself_reaches_once() -> None:
    assert notifications.decision_recipients({"requester_email": "Paul@corp.local", "beneficiary_email": "paul@corp.local"}) == ["Paul@corp.local"]


def test_a_missing_address_is_skipped() -> None:
    assert notifications.decision_recipients({"requester_email": None, "beneficiary_email": "paul@corp.local"}) == ["paul@corp.local"]
    assert notifications.decision_recipients({"requester_email": "", "beneficiary_email": None}) == []


def test_the_decision_is_queued_for_both(monkeypatch) -> None:
    sent: list[tuple[str, list[str]]] = []
    row = {"id": 9, "code": "REQ-9", "root_name": "Finance", "root_path": "\\\\f1\\Finance", "permission": "read", "expires_at": None,
           "decision_comment": None, "requester_email": "manager@corp.local", "beneficiary_email": "paul.martin@corp.local",
           "requester_identity_id": 3}
    monkeypatch.setattr(notifications, "_bell_request_decided", lambda db, request_id, decision: None)
    monkeypatch.setattr(notifications, "settings", lambda db: {"enabled": True, "decisionToRequester": True, "appUrl": ""})
    monkeypatch.setattr(notifications, "_request", lambda db, request_id: row)
    monkeypatch.setattr(notifications, "queue", lambda key, recipients, subject, body, html=None: sent.append((key, recipients)))
    notifications.request_decided(None, 9, "approved")
    assert sent == [("request:9:approved", ["manager@corp.local", "paul.martin@corp.local"])]
