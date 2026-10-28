"""Infrastructure health check run by a worker (Advanced Settings › Infrastructure).

Checks every target from the worker's network position, in parallel:
  tcp  : the port accepts a connection (database, Redis, domain controllers, file servers)
  http : the URL answers (status < 500); https certificate checked unless verify_tls is false
Each target gets healthy / degraded (slow) / down, a latency and a message.
"""
from __future__ import annotations

import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

__test__ = False

SLOW_MS = 1500


def _split_host_port(target: str) -> tuple[str, int]:
    host, _, port = str(target).strip().rpartition(":")
    if not host or not port.isdigit():
        raise ValueError(f"Expected host:port, got {target!r}")
    return host.strip("[]"), int(port)


def _status_for(latency_ms: int) -> str:
    return "degraded" if latency_ms > SLOW_MS else "healthy"


def check_tcp(target: str, timeout: float) -> dict:
    started = time.monotonic()
    try:
        host, port = _split_host_port(target)
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        return {"status": "down", "latency_ms": None, "message": f"Cannot resolve the host: {exc}"}
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency = int((time.monotonic() - started) * 1000)
            return {"status": _status_for(latency), "latency_ms": latency, "message": f"Port {port} open"}
    except socket.timeout:
        return {"status": "down", "latency_ms": None, "message": f"No answer on port {port} (timeout)"}
    except OSError as exc:
        return {"status": "down", "latency_ms": None, "message": f"Port {port} closed or filtered: {exc.strerror or exc}"}


def check_http(url: str, timeout: float, verify_tls: bool) -> dict:
    started = time.monotonic()
    try:
        with httpx.Client(timeout=timeout, verify=verify_tls, follow_redirects=False) as client:
            resp = client.get(url)
    except httpx.ConnectError as exc:
        cause = exc.__cause__ or exc
        if isinstance(cause, ssl.SSLError) or "certificate" in str(exc).lower():
            return {"status": "down", "latency_ms": None, "message": f"Certificate refused: {exc}"}
        return {"status": "down", "latency_ms": None, "message": f"Connection refused: {exc}"}
    except httpx.TimeoutException:
        return {"status": "down", "latency_ms": None, "message": "No answer (timeout)"}
    except httpx.HTTPError as exc:
        return {"status": "down", "latency_ms": None, "message": str(exc)[:300]}
    latency = int((time.monotonic() - started) * 1000)
    if resp.status_code >= 500:
        return {"status": "down", "latency_ms": latency, "message": f"HTTP {resp.status_code}"}
    return {"status": _status_for(latency), "latency_ms": latency, "message": f"HTTP {resp.status_code}"}


def run_infra_health_check(params: dict):
    targets = [t for t in (params.get("targets") or []) if isinstance(t, dict) and t.get("component")]
    timeout = max(1, min(int(params.get("timeout") or 5), 15))
    verify_tls = bool(params.get("verify_tls", True))

    def _one(target: dict) -> dict:
        kind = str(target.get("kind") or "http").lower()
        value = str(target.get("target") or "")
        result = check_tcp(value, timeout) if kind == "tcp" else check_http(value, timeout, verify_tls)
        return {"component": target["component"], "kind": kind, "target": value, **result}

    with ThreadPoolExecutor(max_workers=min(16, max(1, len(targets)))) as pool:
        results = list(pool.map(_one, targets))

    down = [r["component"] for r in results if r["status"] == "down"]
    message = f"{len(results) - len(down)}/{len(results)} components reachable"
    # The check itself succeeded even when components are down: the results carry the states
    return True, message, {"results": results, "checked_by": socket.gethostname(), "down": down}
