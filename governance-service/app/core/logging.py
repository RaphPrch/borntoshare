from __future__ import annotations

import logging
import os
from logging.config import dictConfig

def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s %(name)s - %(message)s"
                }
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "default"}
            },
            "root": {"level": level, "handlers": ["console"]},
        }
    )

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
