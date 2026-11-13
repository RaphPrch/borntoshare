"""The sync of the discovered shares changes the rights only: the last measure of each folder stays."""
from __future__ import annotations

from types import SimpleNamespace

from app.api import storage_roots as api


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class _Db:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        return _Query(self.rows)

    def commit(self):
        pass


def _root(root_id, path):
    measure = {"content_stats": {"files": 144202}, "content_previous": [{"bytes": 1}], "content_size_bytes": 659, "control": "SR|DP"}
    return SimpleNamespace(id=root_id, root_path=path, discovered_permissions_json=dict(measure), last_probe_status=None)


def test_sync_keeps_the_measure(monkeypatch):
    listed, gone = _root(45, "\\\\filer\\DATA"), _root(46, "\\\\filer\\OLD")
    monkeypatch.setattr(api, "ProbeResultService", lambda db: SimpleNamespace(record_storage_root_probe=lambda *a, **k: None))
    monkeypatch.setattr(api, "_persist_endpoint_discovery_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(api, "_reconcile_storage_root_alerts", lambda *a, **k: None)
    payload = api.StorageRootDiscoverySyncPayload(storage_endpoint_id=1, discovery_complete=True,
                                                  roots=[api.StorageRootDiscoveryItem(root_path="\\\\filer\\DATA", permissions=[{"who": "x"}])])
    api.sync_storage_root_discovery(payload, db=_Db([listed, gone]))
    assert listed.discovered_permissions_json["content_stats"] == {"files": 144202}
    assert listed.discovered_permissions_json["content_previous"] and listed.discovered_permissions_json["control"] == "SR|DP"
    assert listed.discovered_permissions_json["permissions"] == [{"who": "x"}]
    # Not listed any more (unreachable now): its rights are unknown, its last measure stays
    assert gone.discovered_permissions_json["content_stats"] == {"files": 144202}
    assert gone.discovered_permissions_json["probe_error"] == "root_not_discovered_or_unreachable"
