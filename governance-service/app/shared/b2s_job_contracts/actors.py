from __future__ import annotations

from dataclasses import dataclass

import dramatiq

from app.jobs.broker import broker as _broker
from app.shared.b2s_job_contracts.contracts import (
    QUEUE_ACL,
    QUEUE_IDENTITY,
    QUEUE_PROBES,
    QUEUE_PROVISIONING,
    actor_for_job_type,
    queue_for_job_type,
)


@dataclass(frozen=True)
class QueuePublisher:
    actor_name: str
    queue_name: str
    max_retries: int = 5

    def send(self, job_id: int) -> None:
        numeric_job_id = int(job_id)
        message = dramatiq.Message(
            queue_name=self.queue_name,
            actor_name=self.actor_name,
            args=(numeric_job_id,),
            kwargs={},
            options={"max_retries": int(self.max_retries)},
        )
        _broker.enqueue(message)


run_identity_job = QueuePublisher(actor_name="run_identity_job", queue_name=QUEUE_IDENTITY)
run_provisioning_job = QueuePublisher(actor_name="run_provisioning_job", queue_name=QUEUE_PROVISIONING)
run_acl_job = QueuePublisher(actor_name="run_acl_job", queue_name=QUEUE_ACL)
run_probe_job = QueuePublisher(actor_name="run_probe_job", queue_name=QUEUE_PROBES)

_PUBLISHERS_BY_ACTOR = {
    "run_identity_job": run_identity_job,
    "run_provisioning_job": run_provisioning_job,
    "run_acl_job": run_acl_job,
    "run_probe_job": run_probe_job,
}


def publish_job(job_type: str | None, job_id: int) -> None:
    numeric_job_id = int(job_id)
    actor_name = actor_for_job_type(job_type)
    publisher = _PUBLISHERS_BY_ACTOR[actor_name]
    if publisher.queue_name != queue_for_job_type(job_type):
        raise RuntimeError(f"Job contract queue mismatch for {job_type}")
    publisher.send(numeric_job_id)
