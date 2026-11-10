"""Passwords read from files (podman secrets mounted in /run/secrets, mode 0400) rather than from the environment of
the container, where `podman inspect` shows them: NAME_FILE=/run/secrets/x gives NAME. Read once, when the package is
imported, before the settings. The same file in every service (a test checks it)."""
from __future__ import annotations

import os
from urllib.parse import quote

NAMES = ("DB_PASSWORD", "LOGGING_DB_PASSWORD", "FIVES_DB_PASSWORD", "REDIS_PASSWORD", "B2S_SECRET_MASTER_KEY")


def load(environ: "os._Environ[str] | dict[str, str]" = os.environ) -> None:
    for name in NAMES:
        path = (environ.get(f"{name}_FILE") or "").strip()
        if path and not environ.get(name):
            with open(path, encoding="utf-8") as handle:
                environ[name] = handle.read().strip()
    # The URL of the job broker carries the Redis password: added here when it is given without one
    url, password = environ.get("CAPSULE_BROKER_URL") or "", environ.get("REDIS_PASSWORD") or ""
    if password and url.startswith("redis://") and "@" not in url:
        environ["CAPSULE_BROKER_URL"] = url.replace("redis://", f"redis://:{quote(password, safe='')}@", 1)
