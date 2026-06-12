from __future__ import annotations

from app.routers import internal_directory_snapshots as module


class _FakeRepo:
    def __init__(self, _db):
        self._db = _db

    def create_run(self, **kwargs):  # noqa: ANN003
        self._db.created = dict(kwargs)
        return {
            "id": 55,
            "snapshot_id": 55,
            "identity_source_id": int(kwargs.get("identity_source_id") or 0),
            "version": 4,
            "status": "CREATED",
        }

    def patch_status(self, *, snapshot_id: int, status: str, summary_json: dict | None, error_message: str | None):
        self._db.patched = {
            "snapshot_id": int(snapshot_id),
            "status": str(status),
            "summary_json": dict(summary_json or {}),
            "error_message": error_message,
        }
        return {
            "id": int(snapshot_id),
            "snapshot_id": int(snapshot_id),
            "identity_source_id": int((self._db.created or {}).get("identity_source_id") or 0),
            "version": 4,
            "status": str(status),
        }


class _FakeDB:
    def __init__(self):
        self.created: dict | None = None
        self.patched: dict | None = None


def test_create_snapshot_run_always_queues_deferred_job(monkeypatch) -> None:
    db = _FakeDB()
    monkeypatch.setattr(module, "DirectorySnapshotsRepo", _FakeRepo)

    out = module.create_snapshot_run(
        module.DirectorySnapshotRunRequest(
            identity_source_id=9,
            initiated_by="gov",
            snapshot_source="governance",
            correlation_id="corr-snap-01",
            mode="full",
            force_full=True,
            deferred=False,
        ),
        db=db,
    )

    assert out.snapshot_id == 55
    assert out.identity_source_id == 9
    assert out.status == "QUEUED"
    assert db.created is not None
    assert db.patched is not None
    assert (db.patched or {}).get("status") == "QUEUED"
    assert bool(((db.patched or {}).get("summary_json") or {}).get("deferred")) is True
    assert ((db.patched or {}).get("summary_json") or {}).get("mode") == "full"
