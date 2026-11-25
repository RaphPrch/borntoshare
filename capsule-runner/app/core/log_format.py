"""Log lines of the services: text (default) or one JSON object per line (LOG_FORMAT=json).

Both carry the context passed with extra= (storage_root_id, job_id, error_code…) and the id of the request being
served; the value of a key that names a secret (password, token, secret, cookie…) is masked.
The same file is in core-service, auth-service and capsule-runner (checked by a test of core-service).
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Callable

_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime", "taskName"}
_SECRET_KEY = re.compile(r"pass(word|wd)?|secret|token|authorization|cookie|api_?key|private_?key|credential", re.I)


def _context(record: logging.LogRecord) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in vars(record).items():
        if key in _STANDARD or key.startswith("_"):
            continue
        out[key] = "***" if _SECRET_KEY.search(key) else value
    return out


def json_enabled() -> bool:
    return os.getenv("LOG_FORMAT", "text").strip().lower() == "json"


class ServiceFormatter(logging.Formatter):
    def __init__(self, service: str, tag: str, request_id: Callable[[], str | None] | None = None, as_json: bool | None = None):
        super().__init__(f"%(asctime)s [%(levelname)s] [{tag}] %(name)s - %(message)s")
        self.service = service
        self.request_id = request_id
        self.as_json = json_enabled() if as_json is None else as_json

    def format(self, record: logging.LogRecord) -> str:
        context = _context(record)
        request_id = self.request_id() if self.request_id else None
        if request_id and "request_id" not in context:
            context["request_id"] = request_id
        record.message = record.getMessage()
        if self.as_json:
            entry: dict[str, object] = {
                "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "service": self.service,
                "logger": record.name,
                "message": record.message,
                **context,
            }
            if record.exc_info:
                entry["exception"] = self.formatException(record.exc_info)
            return json.dumps(entry, default=str, ensure_ascii=False)
        record.asctime = self.formatTime(record, self.datefmt)
        line = self.formatMessage(record)
        if context:
            line += " | " + " ".join(f"{key}={value}" for key, value in context.items())
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        if record.stack_info:
            line += "\n" + self.formatStack(record.stack_info)
        return line


def use_on(logger: logging.Logger, formatter: ServiceFormatter) -> None:
    """The formatter on the console handlers of the logger (the root one, set up by basicConfig or Dramatiq). Only
    plain StreamHandlers: the capture handlers of the tests keep theirs."""
    for handler in logger.handlers:
        if type(handler) is logging.StreamHandler:
            handler.setFormatter(formatter)
