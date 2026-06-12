from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.core.settings import get_settings


settings = get_settings()

broker = RedisBroker(
    url=settings.capsule_broker_url,
)

dramatiq.set_broker(broker)
