from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api import storage_roots
from app.services import features


def _off(monkeypatch):
    monkeypatch.setattr(features, "enabled", lambda db, feature: feature != "fives")


def test_the_sensitivity_scan_is_refused_while_the_5s_module_is_off(monkeypatch):
    _off(monkeypatch)
    payload = storage_roots.SensitivityScanPayload(root_ids=[1])
    with pytest.raises(HTTPException) as refused:
        asyncio.run(storage_roots.scan_sensitivity(payload, request=None, db=object()))
    assert refused.value.status_code == 403 and refused.value.detail["error_code"] == "FEATURE_DISABLED"


def test_ignoring_a_sensitive_file_is_refused_while_the_5s_module_is_off(monkeypatch):
    _off(monkeypatch)
    payload = storage_roots.SensitivityIgnorePayload.model_construct()
    with pytest.raises(HTTPException) as refused:
        storage_roots.ignore_sensitive_file(1, payload, request=None, db=object())
    assert refused.value.status_code == 403 and refused.value.detail["feature"] == "fives"
