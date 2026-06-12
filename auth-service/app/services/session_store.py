from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

from app.core.config import get_settings
from app.core.logging import get_logger, log_event, mask_session_id
from app.schemas.auth import UserInfo

settings = get_settings()
logger = get_logger("session-store")

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore


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
    user: UserInfo
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
    def create(self, user: UserInfo) -> SessionRecord: ...
    def get(self, session_id: str) -> Optional[SessionRecord]: ...
    def delete(self, session_id: str) -> None: ...
    def list(self) -> list[SessionRecord]: ...


# -----------------------------------------------------------
# In-memory session store (V1)
# -----------------------------------------------------------

class InMemorySessionStore:
    """V1 store: process-local in-memory store."""

    def __init__(self) -> None:
        self._data: dict[str, SessionRecord] = {}

    def create(self, user: UserInfo) -> SessionRecord:
        if not isinstance(user, UserInfo):
            # Fail fast: sessions must store the canonical identity object
            raise TypeError("SessionStore.create expects a UserInfo instance")

        sid = str(uuid.uuid4())
        now = _utcnow()

        rec = SessionRecord(
            session_id=sid,
            user=user,
            created_at=now,
            last_seen=now,
        )

        self._data[sid] = rec

        log_event(
            logger,
            logging.DEBUG,
            "AUTH_SESSION_CREATED",
            provider="session_store",
            actor=user.username,
            session_id=mask_session_id(sid),
            outcome="success",
        )

        return rec

    def get(self, session_id: str) -> Optional[SessionRecord]:
        rec = self._data.get(session_id)
        if not rec:
            return None

        if rec.is_expired():
            self._data.pop(session_id, None)
            log_event(
                logger,
                logging.DEBUG,
                "AUTH_SESSION_EXPIRED",
                provider="session_store",
                session_id=mask_session_id(session_id),
                outcome="expired",
            )
            return None

        # Update last_seen
        rec.last_seen = _utcnow()
        return rec

    def delete(self, session_id: str) -> None:
        self._data.pop(session_id, None)

    def list(self) -> list[SessionRecord]:
        # Filter expired and return active sessions
        active: list[SessionRecord] = []
        for sid, rec in list(self._data.items()):
            if rec.is_expired():
                self._data.pop(sid, None)
                log_event(
                    logger,
                    logging.DEBUG,
                    "AUTH_SESSION_EXPIRED",
                    provider="session_store",
                    session_id=mask_session_id(sid),
                    outcome="expired",
                )
                continue
            active.append(rec)
        return active


class RedisSessionStore:
    """Redis-backed session store (shared, multi-instance safe)."""

    def __init__(self) -> None:
        if redis is None:
            raise RuntimeError("redis package is not installed")

        self._key_prefix = str(settings.REDIS_KEY_PREFIX or "bts:auth").strip() or "bts:auth"
        self._session_ttl = int(settings.SESSION_TTL_SECONDS)
        self._idle_timeout = int(settings.SESSION_IDLE_TIMEOUT)
        self._client = redis.Redis(
            host=settings.REDIS_HOST,
            port=int(settings.REDIS_PORT),
            db=int(settings.REDIS_DB),
            username=settings.REDIS_USERNAME,
            password=settings.REDIS_PASSWORD,
            ssl=bool(settings.REDIS_TLS),
            socket_timeout=float(settings.REDIS_TIMEOUT_SECONDS),
            socket_connect_timeout=float(settings.REDIS_TIMEOUT_SECONDS),
            decode_responses=True,
        )

    def _sess_key(self, session_id: str) -> str:
        return f"{self._key_prefix}:sess:{session_id}"

    def _user_sessions_key(self, identity_id: str) -> str:
        return f"{self._key_prefix}:user_sessions:{identity_id}"

    @staticmethod
    def _to_dt(value: str | None) -> datetime:
        if not value:
            return _utcnow()
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _serialize_user(user: UserInfo) -> dict:
        if hasattr(user, "model_dump"):
            return user.model_dump()
        return dict(user)  # pragma: no cover

    @staticmethod
    def _deserialize_user(payload: dict) -> UserInfo:
        if hasattr(UserInfo, "model_validate"):
            return UserInfo.model_validate(payload)
        return UserInfo(**payload)  # pragma: no cover

    def _encode_record(self, rec: SessionRecord) -> str:
        payload = {
            "session_id": rec.session_id,
            "created_at": rec.created_at.isoformat(),
            "last_seen": rec.last_seen.isoformat(),
            "user": self._serialize_user(rec.user),
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    def _decode_record(self, raw: str) -> SessionRecord | None:
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return None
            user_payload = payload.get("user")
            if not isinstance(user_payload, dict):
                return None
            session_id = str(payload.get("session_id") or "").strip()
            if not session_id:
                return None
            rec = SessionRecord(
                session_id=session_id,
                user=self._deserialize_user(user_payload),
                created_at=self._to_dt(payload.get("created_at")),
                last_seen=self._to_dt(payload.get("last_seen")),
            )
            return rec
        except Exception:
            return None

    def _effective_ttl(self, rec: SessionRecord) -> int:
        now = _utcnow()
        hard_left = self._session_ttl - int((now - rec.created_at).total_seconds())
        idle_left = self._idle_timeout - int((now - rec.last_seen).total_seconds())
        ttl = min(hard_left, idle_left)
        return max(1, ttl)

    def create(self, user: UserInfo) -> SessionRecord:
        if not isinstance(user, UserInfo):
            raise TypeError("SessionStore.create expects a UserInfo instance")

        sid = str(uuid.uuid4())
        now = _utcnow()
        rec = SessionRecord(session_id=sid, user=user, created_at=now, last_seen=now)

        key = self._sess_key(sid)
        ttl = self._effective_ttl(rec)
        raw = self._encode_record(rec)
        self._client.set(name=key, value=raw, ex=ttl)

        identity_id = str(user.identity_id or "").strip()
        if identity_id:
            user_sessions_key = self._user_sessions_key(identity_id)
            self._client.sadd(user_sessions_key, sid)
            self._client.expire(user_sessions_key, max(self._session_ttl, self._idle_timeout))

        log_event(
            logger,
            logging.DEBUG,
            "AUTH_SESSION_CREATED",
            provider="session_store",
            actor=user.username,
            session_id=mask_session_id(sid),
            outcome="success",
        )
        return rec

    def get(self, session_id: str) -> Optional[SessionRecord]:
        key = self._sess_key(session_id)
        raw = self._client.get(key)
        if not raw:
            return None

        rec = self._decode_record(raw)
        if not rec:
            self._client.delete(key)
            return None

        if rec.is_expired():
            self.delete(session_id)
            log_event(
                logger,
                logging.DEBUG,
                "AUTH_SESSION_EXPIRED",
                provider="session_store",
                session_id=mask_session_id(session_id),
                outcome="expired",
            )
            return None

        rec.last_seen = _utcnow()
        ttl = self._effective_ttl(rec)
        self._client.set(name=key, value=self._encode_record(rec), ex=ttl)
        return rec

    def delete(self, session_id: str) -> None:
        key = self._sess_key(session_id)
        raw = self._client.get(key)
        if raw:
            rec = self._decode_record(raw)
            if rec:
                identity_id = str(rec.user.identity_id or "").strip()
                if identity_id:
                    self._client.srem(self._user_sessions_key(identity_id), session_id)
        self._client.delete(key)

    def list(self) -> list[SessionRecord]:
        out: list[SessionRecord] = []
        pattern = self._sess_key("*")
        for key in self._client.scan_iter(match=pattern, count=200):
            raw = self._client.get(key)
            if not raw:
                continue
            rec = self._decode_record(raw)
            if not rec:
                self._client.delete(key)
                continue
            if rec.is_expired():
                self.delete(rec.session_id)
                continue
            out.append(rec)
        return out


# -----------------------------------------------------------
# Store factory + SINGLETON GLOBAL
# -----------------------------------------------------------

_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Factory returning a single shared SessionStore instance."""
    global _session_store

    if _session_store is not None:
        return _session_store

    backend = str(getattr(settings, "SESSION_STORE_BACKEND", "memory") or "memory").strip().lower()
    if backend == "redis":
        _session_store = RedisSessionStore()
        outcome = "redis"
        scope = "shared"
    else:
        _session_store = InMemorySessionStore()
        outcome = "inmemory"
        scope = "process_local"

    log_event(
        logger,
        logging.INFO,
        "AUTH_SESSION_STORE_INITIALIZED",
        provider="session_store",
        outcome=outcome,
        scope=scope,
    )
    return _session_store


# 🔥 Canonical instance used everywhere
session_store: SessionStore = get_session_store()
