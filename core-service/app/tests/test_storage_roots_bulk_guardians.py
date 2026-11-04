from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.api import storage_roots as router
from app.data.models.identity import Identity


class _DB:
    def get(self, model, key):
        return Identity(id=int(key), username=f"user-{key}") if model is Identity and int(key) in (7, 9) else None

    def execute(self, *_args, **_kwargs):
        class _Result:
            def scalar(self):
                return 8

        return _Result()


def _batch(guardians: list[int]):
    return router.StorageRootBulkPayload(
        items=[{"storage_endpoint_id": 90, "name": "Paris - Finance", "root_path": "\\\\filer\\Paris\\Finance"}],
        guardian_ids=guardians,
    )


@pytest.fixture
def no_creation(monkeypatch):
    def _refuse(*_args, **_kwargs):
        raise AssertionError("a folder was created although its guardians were refused")

    monkeypatch.setattr(router, "_create_storage_root", _refuse)
    monkeypatch.setattr(router, "min_guardians", lambda _db: 2)
    monkeypatch.setattr(router, "_load_active_enabled_snapshot_users", lambda _db, identity_source_id: {7})


def test_too_few_guardians_refuse_the_batch_before_any_folder(no_creation) -> None:
    with pytest.raises(HTTPException) as refused:
        asyncio.run(router.create_roots_in_bulk(_batch([7]), request=None, db=_DB()))
    assert refused.value.status_code == 422 and refused.value.detail["code"] == "TOO_FEW_GUARDIANS"


def test_a_guardian_outside_the_directory_refuses_the_batch(no_creation) -> None:
    with pytest.raises(HTTPException) as refused:
        asyncio.run(router.create_roots_in_bulk(_batch([7, 9]), request=None, db=_DB()))
    assert refused.value.status_code == 400 and "9" in refused.value.detail
