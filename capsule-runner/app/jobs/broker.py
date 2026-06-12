from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import CurrentMessage

from app.core import settings


broker = RedisBroker(
    url=settings.CAPSULE_BROKER_URL,
)

# Required by `run_job` to read retry metadata from the current message.
broker.add_middleware(CurrentMessage())

dramatiq.set_broker(broker)
