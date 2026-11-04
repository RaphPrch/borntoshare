from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.api import access_requests as api
from app.api import advanced_settings


@pytest.fixture
def policy(monkeypatch):
    current = {"requests": {"durations": [7, 30], "allowPermanent": False, "maxDays": 30, "minReasonLength": 10}}
    monkeypatch.setattr(advanced_settings, "_read_payload", lambda _db: current)
    return current


def _code(callable_) -> str:
    with pytest.raises(HTTPException) as refused:
        callable_()
    return refused.value.detail["code"]


def test_policy_of_the_requests(policy) -> None:
    in_10_days = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    in_60_days = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    api._check_request_policy(None, "Clôture de novembre", in_10_days, [])
    assert _code(lambda: api._check_request_policy(None, "court", in_10_days, [])) == "REQUEST_REASON_TOO_SHORT"
    assert _code(lambda: api._check_request_policy(None, "Clôture de novembre", None, [])) == "REQUEST_PERMANENT_NOT_ALLOWED"
    assert _code(lambda: api._check_request_policy(None, "Clôture de novembre", in_60_days, [])) == "REQUEST_TOO_LONG"
    policy["requests"]["allowPermanent"] = True
    api._check_request_policy(None, "Clôture de novembre", None, [{"expires_at": None}])
