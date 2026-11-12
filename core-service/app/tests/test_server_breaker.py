from datetime import datetime, timedelta

from app.services import server_breaker as sb

NOW = datetime(2026, 11, 12, 12, 0)
DOWN = "SMB storage root read failed: do_connect: Connection to DFS01.corp.local failed (Error NT_STATUS_UNSUCCESSFUL)"
REFUSED = "do_connect: Connection to 172.22.98.56 failed (Error NT_STATUS_CONNECTION_REFUSED)"


def _ago(minutes):
    return NOW - timedelta(minutes=minutes)


def test_the_same_server_has_one_key():
    assert sb.host_key("DFS01.corp.local") == sb.host_key("dfs01") == "dfs01"
    assert sb.host_key("172.22.98.56") == "172.22.98.56"
    assert sb.host_key({"payload": {"target": {"host": "X"}}}.get("none")) == ""
    assert sb.host_of_payload('{"payload": {"target": {"host": "FILER01.corp.local"}}}') == "filer01"


def test_three_connection_failures_in_a_row_put_the_server_down_and_the_wait_doubles():
    two = [("FAILED", DOWN, _ago(1)), ("FAILED", REFUSED, _ago(2)), ("SUCCEEDED", None, _ago(3))]
    assert sb.evaluate(two, NOW)["down"] is False
    three = [("FAILED", DOWN, _ago(1)), ("FAILED", DOWN, _ago(2)), ("FAILED", REFUSED, _ago(3))]
    state = sb.evaluate(three, NOW)
    assert state["down"] and state["waiting"] and state["retry_at"] == _ago(1) + timedelta(minutes=5)
    assert sb.backoff_minutes(4) == 10 and sb.backoff_minutes(20) == 60
    assert sb.evaluate(three, NOW + timedelta(minutes=10))["waiting"] is False  # retry time passed: one job may try


def test_a_refused_password_or_a_success_is_not_a_dead_server():
    rows = [("FAILED", "NT_STATUS_LOGON_FAILURE", _ago(1)), ("FAILED", DOWN, _ago(2)), ("FAILED", DOWN, _ago(3)), ("FAILED", DOWN, _ago(4))]
    assert sb.evaluate(rows, NOW)["failures"] == 0
    assert sb.evaluate([("SUCCEEDED", None, _ago(1)), *rows[1:]], NOW)["down"] is False


def test_the_admin_test_button_is_never_refused(monkeypatch):
    monkeypatch.setattr(sb, "state", lambda db, host: {"down": True, "waiting": True, "failures": 5, "host": "dfs01", "retry_at": NOW})
    sb.guard(None, "DFS01", "admin")
    try:
        sb.guard(None, "DFS01", "data_sync")
    except Exception as exc:
        assert exc.detail["error_code"] == "SERVER_UNREACHABLE" and "dfs01" in exc.detail["message"]
    else:
        raise AssertionError("not refused")


def test_directory_jobs_count_by_their_host_and_their_codes():
    assert sb.host_of_payload({"action": "grant_ad_access", "payload": {"host": "172.22.107.251"}}) == "172.22.107.251"
    rows = [("FAILED", "The domain controller could not be reached", _ago(i), "AD_UNREACHABLE") for i in (1, 2, 3)]
    assert sb.evaluate(rows, NOW)["down"] is True
    assert sb.evaluate([("FAILED", "bind refused", _ago(i), "AD_BIND_FAILED") for i in (1, 2, 3)], NOW)["down"] is False


def test_the_wizard_checks_are_never_refused(monkeypatch):
    monkeypatch.setattr(sb, "state", lambda db, host: {"down": True, "waiting": True, "failures": 5, "host": "ad01", "retry_at": NOW})
    sb.guard(None, "AD01", "wizard")
