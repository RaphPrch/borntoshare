from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException

from app.api import advanced_settings
from app.services import request_deadlines


def test_the_deadlines_come_from_the_request_policy(monkeypatch):
    monkeypatch.setattr(request_deadlines, "_policy", lambda db: {"decisionDays": 5, "escalationDays": 0})
    assert request_deadlines.decision_days(None) == 5
    assert request_deadlines.escalation_days(None) == 0
    monkeypatch.setattr(request_deadlines, "_policy", lambda db: {})
    assert (request_deadlines.decision_days(None), request_deadlines.escalation_days(None)) == (3, 7)


def _policy(**requests):
    return {"requests": {"durations": [7], "allowPermanent": True, "maxDays": 365, "minReasonLength": 10, **requests}}


@pytest.mark.parametrize("requests", [{"decisionDays": 0}, {"decisionDays": 61}, {"decisionDays": 5, "escalationDays": 3}])
def test_a_wrong_deadline_is_refused(requests):
    with pytest.raises(HTTPException):
        advanced_settings._validate_new_sections(None, _policy(**requests), {})


def test_reviewers_are_reminded_and_administrators_told(monkeypatch):
    from app.services import inbox, notifications

    pushed, mailed = [], []
    monkeypatch.setattr(request_deadlines, "_policy", lambda db: {"decisionDays": 3, "escalationDays": 7})
    monkeypatch.setattr(request_deadlines, "_overdue_by_reviewer", lambda db, days: {12: {"identity_id": 12, "email": "g@corp", "overdue": 2}})
    monkeypatch.setattr(request_deadlines, "_escalated", lambda db, days: [{"id": 4, "code": "REQ-4", "root_name": "Finance", "created_at": datetime(2026, 11, 1)}])
    monkeypatch.setattr(notifications, "settings", lambda db: {"enabled": True})
    monkeypatch.setattr(notifications, "_admin_emails", lambda db: ["admin@corp"])
    monkeypatch.setattr(notifications, "queue", lambda key, recipients, *a, **k: mailed.append((key.split(":")[1], recipients)))
    monkeypatch.setattr(inbox, "admins", lambda db: [1])
    monkeypatch.setattr(inbox, "push", lambda db, ids, key, **k: pushed.append((list(ids), key.split(":")[1])))
    done = request_deadlines.overdue_reminders(None)
    assert done == {"reminded": 1, "escalated": 1}
    assert pushed == [([12], "overdue"), ([1], "escalated")]
    assert mailed == [("overdue", ["g@corp"]), ("escalated", ["admin@corp"])]
