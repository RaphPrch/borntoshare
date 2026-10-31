from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture
def rows(monkeypatch: pytest.MonkeyPatch) -> dict:
    """secret_items in memory."""
    from core import store

    data: dict = {}
    monkeypatch.setattr(store, "get", lambda ref: data.get(ref))
    monkeypatch.setattr(
        store, "put", lambda ref, name, iv, ciphertext, key_id: data.__setitem__(ref, {"iv": iv, "ciphertext": ciphertext, "key_id": key_id})
    )
    monkeypatch.setattr(store, "delete", lambda ref: data.pop(ref, None))
    return data
