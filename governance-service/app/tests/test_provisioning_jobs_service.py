from __future__ import annotations

import asyncio

from app.services import provisioning_jobs as svc


def test_create_and_publish_job_dispatches_when_created_false_and_existing_job_is_queueable() -> None:
    calls: dict[str, list] = {"post": [], "actor": []}

    async def _fake_post(path: str, payload: dict, timeout: int = 8):
        calls["post"].append((path, payload, timeout))
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

    out = asyncio.run(
        svc.create_and_publish_job(
            payload={
                "correlation_id": "corr_12345678",
                "job_type": "AD_GROUP_ENSURE",
                "status": "QUEUED",
                "payload_json": {"payload": {"group_name": "B2S_FINANCE_READ"}},
            },
            dal_post_fn=_fake_post,
            actor=_Actor(),
        )
    )

    assert out["job_id"] == 1234
    assert calls["post"][0][0] == "/api/internal/provisioning/jobs"
    assert calls["actor"] == [1234]


def test_create_and_publish_job_skips_dispatch_when_created_false_and_terminal_status() -> None:
    calls: dict[str, list] = {"post": [], "actor": []}

    async def _fake_post(path: str, payload: dict, timeout: int = 8):
        calls["post"].append((path, payload, timeout))
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

    out = asyncio.run(
        svc.create_and_publish_job(
            payload={
                "correlation_id": "corr_22222222",
                "job_type": "AD_GROUP_ENSURE",
                "status": "QUEUED",
                "payload_json": {"payload": {"group_name": "B2S_FINANCE_READ"}},
            },
            dal_post_fn=_fake_post,
            actor=_Actor(),
        )
    )

    assert out["job_id"] == 2222
    assert calls["post"][0][0] == "/api/internal/provisioning/jobs"
    assert calls["actor"] == []


def test_create_and_publish_job_normalizes_payload_to_envelope_and_default_metrics() -> None:
    calls: dict[str, list] = {"post": [], "actor": []}

    async def _fake_post(path: str, payload: dict, timeout: int = 8):
        calls["post"].append((path, payload, timeout))
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
            dal_post_fn=_fake_post,
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


def test_create_and_publish_job_rejects_legacy_flat_payload_json() -> None:
    async def _fake_post(path: str, payload: dict, timeout: int = 8):  # pragma: no cover - should not be called
        _ = path, payload, timeout
        raise AssertionError("dal_post must not be called when payload envelope is invalid")

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
                dal_post_fn=_fake_post,
                actor=None,
            )
        )
        raise AssertionError("Expected RuntimeError")
    except RuntimeError as exc:
        assert str(exc) == "GOVERNANCE_JOB_PAYLOAD_ENVELOPE_REQUIRED"


def test_create_and_publish_job_rejects_unknown_job_type_before_dal_write() -> None:
    async def _fake_post(path: str, payload: dict, timeout: int = 8):  # pragma: no cover - should not be called
        _ = path, payload, timeout
        raise AssertionError("dal_post must not be called when job_type is unsupported")

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
                dal_post_fn=_fake_post,
                actor=None,
            )
        )
        raise AssertionError("Expected RuntimeError")
    except RuntimeError as exc:
        assert str(exc) == "GOVERNANCE_JOB_TYPE_UNSUPPORTED"
