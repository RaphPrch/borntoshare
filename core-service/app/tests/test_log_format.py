"""Lines of the logs: the context of extra= kept (text and JSON), secrets masked, the same formatter in the
three services."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.log_format import ServiceFormatter

ROOT = Path(__file__).resolve().parents[3]


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord("core.jobs", logging.WARNING, __file__, 1, "JOB_STUCK", (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_text_lines_keep_the_context_given_with_extra() -> None:
    line = ServiceFormatter("core-service", "CORE", as_json=False).format(_record(job_id=12, storage_root_id=4))
    assert "[CORE] core.jobs - JOB_STUCK | job_id=12 storage_root_id=4" in line


def test_json_lines_carry_service_level_context_and_request_id() -> None:
    formatter = ServiceFormatter("core-service", "CORE", request_id=lambda: "req-1", as_json=True)
    entry = json.loads(formatter.format(_record(job_id=12)))
    assert entry["service"] == "core-service" and entry["level"] == "WARNING" and entry["logger"] == "core.jobs"
    assert entry["message"] == "JOB_STUCK" and entry["job_id"] == 12 and entry["request_id"] == "req-1"
    assert entry["ts"].endswith("+00:00")


def test_values_of_secret_keys_are_masked_in_both_formats() -> None:
    record = _record(bind_password="hunter2", internal_token="abc", api_key="k", user="alice")
    text = ServiceFormatter("core-service", "CORE", as_json=False).format(record)
    entry = json.loads(ServiceFormatter("core-service", "CORE", as_json=True).format(record))
    assert "hunter2" not in text and "abc" not in text and "user=alice" in text
    assert entry["bind_password"] == entry["internal_token"] == entry["api_key"] == "***" and entry["user"] == "alice"


def test_an_exception_is_kept_in_json() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        import sys

        record = logging.LogRecord("core.x", logging.ERROR, __file__, 1, "FAILED", (), sys.exc_info())
    entry = json.loads(ServiceFormatter("core-service", "CORE", as_json=True).format(record))
    assert "RuntimeError: boom" in entry["exception"]


def test_the_three_services_have_the_same_formatter() -> None:
    reference = (ROOT / "core-service/app/core/log_format.py").read_text()
    for service in ("auth-service", "capsule-runner"):
        assert (ROOT / service / "app/core/log_format.py").read_text() == reference, service
