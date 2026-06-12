from __future__ import annotations

from app.services import activity_log


def test_log_activity_submits_payload_and_sets_marker(monkeypatch) -> None:
    captured: list[dict] = []

    class _FakeExecutor:
        def submit(self, fn, payload):
            captured.append(payload)
            fn(payload)

    monkeypatch.setattr(activity_log, "_activity_executor", _FakeExecutor())
    monkeypatch.setattr(activity_log, "write_activity_event", lambda **kwargs: {"ok": True})

    activity_log.reset_activity_marker()
    assert activity_log.has_activity_marker() is False

    result = activity_log.log_activity(
        None,
        actor_type="user",
        actor_id=10,
        actor_display="alice",
        action="identity_source.updated",
        outcome="success",
        target_type="identity_source",
        target_id=5,
        target_display="src-5",
        context_json={"k": "v"},
        correlation_id="rid-1",
    )

    assert result == {"ok": True, "queued": True}
    assert activity_log.has_activity_marker() is True
    assert len(captured) == 1
    assert captured[0]["action"] == "identity_source.updated"
    assert captured[0]["correlation_id"] == "rid-1"


def test_write_activity_safe_handles_bridge_rejection(monkeypatch) -> None:
    events: list[str] = []

    monkeypatch.setattr(activity_log, "write_activity_event", lambda **kwargs: {"ok": False, "reason": "denied"})
    monkeypatch.setattr(
        activity_log,
        "log_event",
        lambda _logger, _level, event_name, **_fields: events.append(event_name),
    )

    activity_log._write_activity_safe(
        {
            "actor_type": "system",
            "actor_id": None,
            "actor_display": None,
            "action": "x",
            "outcome": "failed",
            "target_type": None,
            "target_id": None,
            "target_display": None,
            "context_json": None,
            "correlation_id": None,
        }
    )

    assert "DAL_ACTIVITY_WRITE_REJECTED" in events


def test_write_activity_safe_handles_bridge_exception(monkeypatch) -> None:
    events: list[str] = []

    def _raise(**_kwargs):
        raise RuntimeError("bridge down")

    monkeypatch.setattr(activity_log, "write_activity_event", _raise)
    monkeypatch.setattr(
        activity_log,
        "log_event",
        lambda _logger, _level, event_name, **_fields: events.append(event_name),
    )

    activity_log._write_activity_safe(
        {
            "actor_type": "system",
            "actor_id": None,
            "actor_display": None,
            "action": "x",
            "outcome": "failed",
            "target_type": None,
            "target_id": None,
            "target_display": None,
            "context_json": None,
            "correlation_id": None,
        }
    )

    assert "DAL_ACTIVITY_WRITE_FAILED" in events

