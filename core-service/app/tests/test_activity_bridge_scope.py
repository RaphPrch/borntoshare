from __future__ import annotations

from app.services import activity_bridge


def test_the_folder_zone_and_server_of_an_event_come_from_its_context(monkeypatch) -> None:
    written: list[dict] = []
    monkeypatch.setattr(activity_bridge, "create_activity_event", lambda payload: written.append(payload) or {"ok": True})

    def write(context):
        activity_bridge.write_activity_event(
            actor_type="user", actor_id=1, actor_display="a", action="access_request.approve", outcome="success",
            target_type="access_request", target_id=7, target_display="REQ-7", context_json=context, correlation_id=None,
        )
        return written[-1]

    event = write({"storage_root_id": 42, "zone_id": 3, "storage_endpoint_id": 9, "root": "Finance"})
    assert (event["root_id"], event["zone_id"], event["endpoint_id"]) == (42, 3, 9)
    assert event["entity_type"] == "access_request" and event["metadata_json"]["root"] == "Finance"

    plain = write({"root": "Finance", "storage_root_id": "42", "zone_id": True})
    assert "root_id" not in plain and "zone_id" not in plain


def test_an_event_about_a_folder_is_in_its_scope(monkeypatch) -> None:
    written: list[dict] = []
    monkeypatch.setattr(activity_bridge, "create_activity_event", lambda payload: written.append(payload) or {"ok": True})
    activity_bridge.write_activity_event(
        actor_type="user", actor_id=1, actor_display="a", action="storage_root.created", outcome="success",
        target_type="storage_root", target_id=2800, target_display="PiloteTestAD", context_json={"zone_id": 53}, correlation_id=None,
    )
    assert (written[-1]["root_id"], written[-1]["zone_id"]) == (2800, 53)


def test_an_event_about_a_server_is_in_its_scope(monkeypatch) -> None:
    written: list[dict] = []
    monkeypatch.setattr(activity_bridge, "create_activity_event", lambda payload: written.append(payload) or {"ok": True})
    activity_bridge.write_activity_event(
        actor_type="user", actor_id=1, actor_display="a", action="storage_endpoint.dfs_created", outcome="success",
        target_type="storage_endpoint", target_id="207", target_display="brest", context_json={}, correlation_id=None,
    )
    assert written[-1]["endpoint_id"] == 207
