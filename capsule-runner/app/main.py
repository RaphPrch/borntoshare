from __future__ import annotations

import hmac
import logging
import os
import platform
import socket
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core import settings
from app.core.api_envelope import ok_data

raw_level = os.getenv("LOG_LEVEL", "INFO").upper()
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

_basic = HTTPBasic(auto_error=False)


def require_agent_credentials(credentials: HTTPBasicCredentials | None = Depends(_basic)) -> str:
    """Basic authentication with AGENT_USERNAME / AGENT_PASSWORD (constant-time comparison)."""
    if not settings.AGENT_USERNAME or not settings.AGENT_PASSWORD:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent credentials are not configured")
    valid = credentials is not None and all(
        (
            hmac.compare_digest(credentials.username.encode(), settings.AGENT_USERNAME.encode()),
            hmac.compare_digest(credentials.password.encode(), settings.AGENT_PASSWORD.encode()),
        )
    )
    if not valid:
        logger.warning("AGENT_AUTH_FAILED")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


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
def agent_info(_user: str = Depends(require_agent_credentials)):
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
            "ldap_tls_verify": settings.LDAP_TLS_VERIFY,
            "ldap_ca_file_present": bool(settings.LDAP_CA_FILE and os.path.isfile(settings.LDAP_CA_FILE)),
            "agent_tls": bool(settings.AGENT_TLS_CERT and settings.AGENT_TLS_KEY),
        }
    )
