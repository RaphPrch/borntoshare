from __future__ import annotations

import hashlib
import hmac
import logging
import os
import platform
import socket
import time
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status

from app.core import settings
from app.core.api_envelope import ok_data



def _configured_log_level() -> str:
    """Level chosen in Advanced settings > Logging; LOG_LEVEL when core-service does not answer. Read at start."""
    try:
        resp = httpx.get(
            f"{settings.CORE_URL}/api/admin/config/advanced",
            headers={"X-Internal-Token": settings.INTERNAL_TOKEN or ""},
            timeout=2.0,
        )
        level_name = (resp.json().get("data") or {}).get("logging", {}).get("level")
        if resp.status_code == 200 and level_name:
            return str(level_name)
    except (httpx.HTTPError, ValueError, AttributeError):
        pass
    return os.getenv("LOG_LEVEL", "INFO")


raw_level = _configured_log_level().upper()
level = getattr(logging, raw_level, logging.INFO)

logging.basicConfig(
    level=level,
    format="%(asctime)s [%(levelname)s] [RUNNER] %(name)s - %(message)s",
)
logging.getLogger().setLevel(level)

logger = logging.getLogger("capsule-runner")

STARTED_AT = time.time()

app = FastAPI(
    title="BornToShare Capsule Runner",
    version="v1",
    description=(
        "BornToShare Capsule Runner worker runtime (Community v1).\n\n"
        "This service executes jobs from queue as a Dramatiq worker. "
        "HTTP surface is limited to health checks and the authenticated agent API "
        "used by core-service (Advanced Settings › Infrastructure)."
    ),
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

def require_agent_token(x_agent_token: str = Header(default="")) -> None:
    """Only core-service: it derives this proof from INTERNAL_TOKEN (constant-time comparison)."""
    if not settings.INTERNAL_TOKEN:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="INTERNAL_TOKEN is not configured")
    expected = hmac.new(settings.INTERNAL_TOKEN.encode(), b"b2s-agent", hashlib.sha256).hexdigest()
    if not hmac.compare_digest(x_agent_token.encode(), expected.encode()):
        logger.warning("AGENT_AUTH_FAILED")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")


def _dramatiq_processes() -> int:
    count = 0
    for cmdline in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            if b"dramatiq" in cmdline.read_bytes():
                count += 1
        except OSError:
            continue
    return count


def _broker_state() -> dict:
    from redis import Redis

    from app.shared.b2s_job_contracts.contracts import QUEUE_ACL, QUEUE_IDENTITY, QUEUE_PROBES, QUEUE_PROVISIONING

    started = time.monotonic()
    try:
        client = Redis.from_url(settings.CAPSULE_BROKER_URL, socket_timeout=3, socket_connect_timeout=3)
        client.ping()
        latency = int((time.monotonic() - started) * 1000)
        # Dramatiq keeps the waiting messages of a queue in the list "dramatiq:<queue>"
        queues = {q: int(client.llen(f"dramatiq:{q}")) for q in (QUEUE_IDENTITY, QUEUE_PROVISIONING, QUEUE_ACL, QUEUE_PROBES)}
        return {"reachable": True, "latency_ms": latency, "queues": queues}
    except Exception as exc:
        return {"reachable": False, "error": str(exc)[:300]}


@app.get("/health")
def health():
    return ok_data({"status": "ok", "max_scope": settings.RUNNER_MAX_SCOPE, "version": settings.APP_VERSION})


@app.get("/agent/v1/info")
def agent_info(_auth: None = Depends(require_agent_token)):
    """State of this worker, read by core-service: processes, job queue, TLS material."""
    processes = _dramatiq_processes()
    broker = _broker_state()
    healthy = processes > 0 and broker.get("reachable") is True
    return ok_data(
        {
            "status": "healthy" if healthy else "degraded",
            "hostname": socket.gethostname(),
            "version": settings.APP_VERSION,
            "max_scope": settings.RUNNER_MAX_SCOPE,
            "uptime_seconds": int(time.time() - STARTED_AT),
            "python": platform.python_version(),
            "worker_processes": processes,
            "broker": broker,
            "agent_tls": bool(settings.AGENT_TLS_CERT and settings.AGENT_TLS_KEY),
        }
    )
