from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

@dataclass
class KcState:
    state: str
    code_verifier: str
    created_at: datetime

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) - self.created_at > timedelta(seconds=settings.KEYCLOAK_STATE_TTL_SECONDS)

class KeycloakStateStore:
    def __init__(self) -> None:
        self._data: Dict[str, KcState] = {}

    def create(self) -> KcState:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        rec = KcState(state=state, code_verifier=verifier, created_at=datetime.now(timezone.utc))
        self._data[state] = rec
        logger.debug("KC state created | state=%s", state)
        return rec

    def pop(self, state: str) -> Optional[KcState]:
        rec = self._data.pop(state, None)
        if not rec:
            return None
        if rec.is_expired():
            logger.info("KC state expired | state=%s", state)
            return None
        return rec

kc_state_store = KeycloakStateStore()
