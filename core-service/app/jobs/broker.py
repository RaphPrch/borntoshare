from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.core.config import get_settings


settings = get_settings()
if not settings.CAPSULE_BROKER_URL:
    raise RuntimeError("CAPSULE_BROKER_URL is required")

broker = RedisBroker(
    url=settings.CAPSULE_BROKER_URL,
)

dramatiq.set_broker(broker)
