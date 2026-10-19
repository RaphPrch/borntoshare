from __future__ import annotations

import asyncio

from app.services import provisioning_jobs as svc
from app.tests.governance.route_fakes import fake_routes


def test_create_and_publish_job_dispatches_when_created_false_and_existing_job_is_queueable(monkeypatch) -> None:
    calls: dict[str, list] = {"post": [], "actor": []}

    async def _fake_post(path: str, payload: dict):
        calls["post"].append((path, payload))
        return {
            "created": False,
            "data": {
                "id": 1234,
                "status": "QUEUED",
            },
        }

    class _Actor:
        @staticmethod
        def send(job_id: int):
            calls["actor"].append(job_id)

    fake_routes(monkeypatch, svc, post=_fake_post)
    out = asyncio.run(
        svc.create_and_publish_job(
            payload={
                "correlation_id": "corr_12345678",
                "job_type": "AD_GROUP_ENSURE",
                "status": "QUEUED",
                "payload_json": {"payload": {"group_name": "B2S_FINANCE_READ"}},
            },
            actor=_Actor(),
        )
    )

    assert out["job_id"] == 1234
    assert calls["post"][0][0] == "/api/internal/provisioning/jobs"
    assert calls["actor"] == [1234]


def test_create_and_publish_job_skips_dispatch_when_created_false_and_terminal_status(monkeypatch) -> None:
    calls: dict[str, list] = {"post": [], "actor": []}

    async def _fake_post(path: str, payload: dict):
        calls["post"].append((path, payload))
        return {
            "created": False,
            "data": {
                "id": 2222,
                "status": "SUCCEEDED",
            },
        }

    class _Actor:
        @staticmethod
        def send(job_id: int):
            calls["actor"].append(job_id)

    fake_routes(monkeypatch, svc, post=_fake_post)
    out = asyncio.run(
        svc.create_and_publish_job(
            payload={
                "correlation_id": "corr_22222222",
                "job_type": "AD_GROUP_ENSURE",
                "status": "QUEUED",
                "payload_json": {"payload": {"group_name": "B2S_FINANCE_READ"}},
            },
            actor=_Actor(),
        )
    )

    assert out["job_id"] == 2222
    assert calls["post"][0][0] == "/api/internal/provisioning/jobs"
    assert calls["actor"] == []


def test_create_and_publish_job_normalizes_payload_to_envelope_and_default_metrics(monkeypatch) -> None:
    calls: dict[str, list] = {"post": [], "actor": []}

    async def _fake_post(path: str, payload: dict):
        calls["post"].append((path, payload))
        return {
            "created": True,
            "data": {
                "id": 3333,
                "status": "QUEUED",
            },
        }

    class _Actor:
        @staticmethod
        def send(job_id: int):
            calls["actor"].append(job_id)

    fake_routes(monkeypatch, svc, post=_fake_post)
    out = asyncio.run(
        svc.create_and_publish_job(
            payload={
                "correlation_id": "corr_33333333",
                "job_type": "AD_GROUP_ENSURE",
                "status": "QUEUED",
                "payload_json": {
                    "payload": {
                        "group_name": "B2S_FINANCE_READ",
                    },
                },
            },
            actor=_Actor(),
        )
    )

    assert out["job_id"] == 3333
    assert calls["actor"] == [3333]

    posted = calls["post"][0][1]
    assert posted["payload_json"]["action"] == "ensure_ad_group"
    assert posted["payload_json"]["payload"]["group_name"] == "B2S_FINANCE_READ"
    assert posted["payload_json"]["payload"]["template"]["slug"] == "ensure_ad_group"

    metrics = posted["metrics_json"]
    assert metrics["submitted_by"] == "governance"
    assert metrics["dispatch_policy"] == "idempotent_recover"
    assert metrics["job_type"] == "AD_GROUP_ENSURE"
    assert metrics["action"] == "ensure_ad_group"


def test_create_and_publish_job_rejects_legacy_flat_payload_json(monkeypatch) -> None:
    async def _fake_post(path: str, payload: dict):  # pragma: no cover - should not be called
        _ = path, payload
        raise AssertionError("the job must not be created when payload envelope is invalid")

    fake_routes(monkeypatch, svc, post=_fake_post)
    try:
        asyncio.run(
            svc.create_and_publish_job(
                payload={
                    "correlation_id": "corr_44444444",
                    "job_type": "AD_GROUP_ENSURE",
                    "status": "QUEUED",
                    "payload_json": {
                        "group_name": "B2S_FINANCE_READ",
                    },
                },
                actor=None,
            )
        )
        raise AssertionError("Expected RuntimeError")
    except RuntimeError as exc:
        assert str(exc) == "GOVERNANCE_JOB_PAYLOAD_ENVELOPE_REQUIRED"


def test_create_and_publish_job_rejects_unknown_job_type_before_core_write(monkeypatch) -> None:
    async def _fake_post(path: str, payload: dict):  # pragma: no cover - should not be called
        _ = path, payload
        raise AssertionError("the job must not be created when job_type is unsupported")

    fake_routes(monkeypatch, svc, post=_fake_post)
    try:
        asyncio.run(
            svc.create_and_publish_job(
                payload={
                    "correlation_id": "corr_55555555",
                    "job_type": "UNKNOWN_JOB",
                    "action": "ensure_ad_group",
                    "status": "QUEUED",
                    "payload_json": {"payload": {"group_name": "B2S_FINANCE_READ"}},
                },
                actor=None,
            )
        )
        raise AssertionError("Expected RuntimeError")
    except RuntimeError as exc:
        assert str(exc) == "GOVERNANCE_JOB_TYPE_UNSUPPORTED"
