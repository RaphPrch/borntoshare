from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core import errors
from app.services import activity_log, audit_logger


@pytest.mark.parametrize(
    "value,expected",
    [("success", "success"), ("denied", "denied"), ("blocked", "denied"), ("error", "failure"), ("started", "in_progress"), ("nimporte", "failure")],
)
def test_an_unplanned_outcome_is_never_a_success(value, expected) -> None:
    assert audit_logger._normalize_result(value) == expected


def _request(method: str, path: str) -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": [(b"x-identity-id", b"7")], "query_string": b"", "server": ("x", 80), "scheme": "http"})


def test_a_refused_change_is_logged_but_not_a_read_nor_an_internal_call(monkeypatch) -> None:
    rows: list[dict] = []
    monkeypatch.setattr(activity_log, "log_activity", lambda db, **kwargs: rows.append(kwargs))

    errors._log_refusal(_request("POST", "/api/zones"), 409, "ZONE_EXISTS", "dup")
    assert rows[0]["action"] == "request.refused" and rows[0]["outcome"] == "failure" and rows[0]["actor_id"] == 7

    errors._log_refusal(_request("DELETE", "/api/x"), 403, "NO", "no")
    assert rows[1]["outcome"] == "denied"

    errors._log_refusal(_request("GET", "/api/zones"), 403, "NO", "no")
    errors._log_refusal(_request("POST", "/api/internal/jobs"), 409, "NO", "no")
    errors._log_refusal(_request("POST", "/api/zones"), 404, "NO", "no")
    assert len(rows) == 2
