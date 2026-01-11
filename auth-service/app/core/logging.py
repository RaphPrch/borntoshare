from __future__ import annotations

import logging
from typing import Optional

from app.core.config import get_settings

_LEVEL_MAP = {
    "ERR": "ERROR",
    "ERROR": "ERROR",
    "WARN": "WARNING",
    "WARNING": "WARNING",
    "INFO": "INFO",
    "DEBUG": "DEBUG",
    "TRACE": "DEBUG",
}

def setup_logging() -> None:
    s = get_settings()
    lvl = (s.B2S_LOG_LEVEL or s.LOG_LEVEL or "INFO").upper()
    lvl = _LEVEL_MAP.get(lvl, lvl)
    if s.B2S_DEBUG:
        lvl = "DEBUG"

    logging.basicConfig(
        level=getattr(logging, lvl, logging.INFO),
        format="[%(asctime)s] [AUTH] [%(levelname)s] %(name)s - %(message)s",
    )

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
