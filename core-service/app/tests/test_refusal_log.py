from __future__ import annotations

from types import SimpleNamespace

from app.core import errors
from app.services import activity_log


def _request(path: str, **state):
    return SimpleNamespace(method="DELETE", url=SimpleNamespace(path=path), headers={}, state=SimpleNamespace(**state))


def test_a_refusal_shows_in_the_activity_of_its_object(monkeypatch) -> None:
    logged: list[dict] = []
    monkeypatch.setattr(activity_log, "log_activity", lambda _db, **kw: logged.append(kw))
    errors._log_refusal(_request("/api/storage-roots/1710"), 409, "STORAGE_ROOT_HAS_ACCESSES", "2 active access(es)")
    assert (logged[-1]["target_type"], logged[-1]["target_id"]) == ("storage_root", 1710)


def test_a_refusal_already_logged_by_its_route_is_not_logged_twice(monkeypatch) -> None:
    logged: list[dict] = []
    monkeypatch.setattr(activity_log, "log_activity", lambda _db, **kw: logged.append(kw))
    errors._log_refusal(_request("/api/storage-endpoints/90/shares", refusal_logged=True), 422, "SHARE_NAME_INVALID", "x")
    assert logged == []
