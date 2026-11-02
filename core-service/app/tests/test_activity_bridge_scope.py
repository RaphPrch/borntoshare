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
