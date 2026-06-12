from __future__ import annotations

from app.security.audit_hash import compute_event_hash


def test_compute_event_hash_is_deterministic() -> None:
    payload = {
        "event_type": "profile_created",
        "target_type": "storage_root_access_profile",
        "target_id": 10,
        "payload_json": {"k": "v", "n": 1},
    }
    h1 = compute_event_hash("abc", payload)
    h2 = compute_event_hash("abc", payload)
    assert h1 == h2
    assert len(h1) == 64


def test_compute_event_hash_changes_with_prev_hash() -> None:
    payload = {
        "event_type": "profile_created",
        "target_type": "storage_root_access_profile",
        "target_id": 10,
        "payload_json": {"k": "v"},
    }
    h1 = compute_event_hash(None, payload)
    h2 = compute_event_hash(h1, payload)
    assert h1 != h2
