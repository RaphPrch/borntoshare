# capsule-runner/settings.py
from __future__ import annotations

import os


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


# ==========================================================
# 🔐 Secret Broker (V1)
# ==========================================================
INTERNAL_TOKEN: str | None = (_env("INTERNAL_TOKEN") or None)


# ==========================================================
# 🧠 Execution scope (V1)
# ==========================================================
# Allowed values: read | write | admin
RUNNER_MAX_SCOPE: str = (_env("RUNNER_MAX_SCOPE", "write") or "write").lower()

if RUNNER_MAX_SCOPE not in {"read", "write"}:
    raise RuntimeError(
        f"Invalid RUNNER_MAX_SCOPE: {RUNNER_MAX_SCOPE} (expected read|write)"
    )



# ==========================================================
# 🗄️ core-service + queue (Dramatiq)
# ==========================================================
CORE_URL: str = (_env("CORE_URL", "http://core-service:8000") or "").rstrip("/")
CAPSULE_BROKER_URL: str = (_env("CAPSULE_BROKER_URL") or "").strip()

if not CAPSULE_BROKER_URL:
    raise RuntimeError("CAPSULE_BROKER_URL is required")


# ==========================================================
# 🛰️ Agent (Advanced Settings › Infrastructure)
# ==========================================================
# Checked by core-service. HTTPS on 8443 when capsule-runner/certs holds agent.crt and agent.key
# (mounted on /etc/b2s/certs), else HTTP on 8080: internal network only.
CERTS_DIR = "/etc/b2s/certs"
AGENT_TLS_CERT: str | None = f"{CERTS_DIR}/agent.crt" if os.path.isfile(f"{CERTS_DIR}/agent.crt") and os.path.isfile(f"{CERTS_DIR}/agent.key") else None
AGENT_TLS_KEY: str | None = f"{CERTS_DIR}/agent.key" if AGENT_TLS_CERT else None
AGENT_PORT: int = 8443 if AGENT_TLS_CERT else 8080
APP_VERSION: str = (_env("APP_VERSION", "v1") or "v1").strip()
