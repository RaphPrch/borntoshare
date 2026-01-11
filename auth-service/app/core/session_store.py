from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol, Any

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("session-store")


# -----------------------------------------------------------
# Helpers
# -----------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# -----------------------------------------------------------
# Session record
# -----------------------------------------------------------

@dataclass
class SessionRecord:
    session_id: str
    user: dict[str, Any]
    created_at: datetime
    last_seen: datetime

    def is_expired(self) -> bool:
        now = _utcnow()

        # Hard TTL
        if now - self.created_at > timedelta(seconds=settings.SESSION_TTL_SECONDS):
            return True

        # Idle timeout
        if now - self.last_seen > timedelta(seconds=settings.SESSION_IDLE_TIMEOUT):
            return True

        return False


# -----------------------------------------------------------
# Protocol
# -----------------------------------------------------------

class SessionStore(Protocol):
    def create(self, user: Any) -> SessionRecord: ...
    def get(self, session_id: str) -> Optional[SessionRecord]: ...
    def delete(self, session_id: str) -> None: ...


# -----------------------------------------------------------
# In-memory session store
# -----------------------------------------------------------

class InMemorySessionStore:
    def __init__(self) -> None:
        self._data: dict[str, SessionRecord] = {}

    def create(self, user: Any) -> SessionRecord:
        sid = str(uuid.uuid4())
        now = _utcnow()

        # Normalize user → dict
        if hasattr(user, "model_dump"):
            user = user.model_dump()
        elif hasattr(user, "dict"):
            user = user.dict()

        rec = SessionRecord(
            session_id=sid,
            user=user,
            created_at=now,
            last_seen=now,
        )

        self._data[sid] = rec

        logger.debug(
            "SESSION_CREATED store=inmemory sid=%s user=%s",
            sid,
            user.get("username"),
        )

        return rec

    def get(self, session_id: str) -> Optional[SessionRecord]:
        rec = self._data.get(session_id)
        if not rec:
            return None

        if rec.is_expired():
            self._data.pop(session_id, None)
            logger.debug("SESSION_EXPIRED store=inmemory sid=%s", session_id)
            return None

        # Update last_seen
        rec.last_seen = _utcnow()
        return rec

    def delete(self, session_id: str) -> None:
        self._data.pop(session_id, None)


# -----------------------------------------------------------
# Redis session store
# -----------------------------------------------------------

class RedisSessionStore:
    def __init__(self) -> None:
        import redis  # type: ignore
        self.redis = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )

    def create(self, user: Any) -> SessionRecord:
        sid = str(uuid.uuid4())
        now = _utcnow()

        if hasattr(user, "model_dump"):
            user = user.model_dump()
        elif hasattr(user, "dict"):
            user = user.dict()

        rec = SessionRecord(
            session_id=sid,
            user=user,
            created_at=now,
            last_seen=now,
        )

        payload = json.dumps(
            {
                "session_id": sid,
                "user": user,
                "created_at": now.isoformat(),
                "last_seen": now.isoformat(),
            }
        )

        self.redis.setex(sid, settings.SESSION_TTL_SECONDS, payload)

        logger.debug(
            "SESSION_CREATED store=redis sid=%s user=%s",
            sid,
            user.get("username"),
        )

        return rec

    def get(self, session_id: str) -> Optional[SessionRecord]:
        raw = self.redis.get(session_id)
        if not raw:
            return None

        data = json.loads(raw)

        rec = SessionRecord(
            session_id=session_id,
            user=data["user"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_seen=datetime.fromisoformat(data["last_seen"]),
        )

        if rec.is_expired():
            self.redis.delete(session_id)
            logger.debug("SESSION_EXPIRED store=redis sid=%s", session_id)
            return None

        # Update last_seen
        rec.last_seen = _utcnow()
        data["last_seen"] = rec.last_seen.isoformat()

        # Refresh TTL
        self.redis.setex(session_id, settings.SESSION_TTL_SECONDS, json.dumps(data))

        return rec

    def delete(self, session_id: str) -> None:
        self.redis.delete(session_id)


# -----------------------------------------------------------
# Store factory + SINGLETON GLOBAL
# -----------------------------------------------------------

_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """
    Factory returning a SINGLE shared SessionStore instance.
    Never creates more than one store per process.
    """
    global _session_store

    if _session_store is not None:
        return _session_store

    store_type = (settings.SESSION_STORE or "inmemory").lower()

    if store_type == "redis":
        _session_store = RedisSessionStore()
    else:
        _session_store = InMemorySessionStore()

    logger.info("SESSION_STORE_INITIALIZED type=%s", store_type)
    return _session_store


# 🔥 Canonical instance used everywhere
session_store: SessionStore = get_session_store()
