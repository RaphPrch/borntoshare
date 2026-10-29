"""Infrastructure health check run by a worker (Advanced Settings › Infrastructure).

Checks every target from the worker's network position, in parallel:
  tcp  : the port accepts a connection (database, Redis, file servers)
  ldap : the domain controller answers as a directory: TLS (checked as for snapshots), bind with the
         account that reads the directory, base DN readable
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


def check_ldap(target: dict, password: str | None, timeout: float) -> dict:
    from app.actions.ldap_test import test_ldap_bind

    if not password:
        return {"status": "down", "latency_ms": None, "message": "The password of the directory account could not be read from the secret broker"}
    host, port = _split_host_port(str(target.get("target") or ""))
    ok, message, details = test_ldap_bind({
        "host": host, "port": port, "use_ssl": bool(target.get("use_ssl", True)),
        "username": target.get("bind_dn"), "password": password, "base_dn": target.get("base_dn"), "timeout": timeout,
    })
    latency = int(details.get("duration_ms") or 0)
    if not ok:
        return {"status": "down", "latency_ms": None, "message": str(details.get("hint") or message), "failure_code": details.get("failure_code")}
    tls = "LDAPS, certificate checked" if details.get("tls_verified") else ("LDAPS" if details.get("use_ssl") else "LDAP")
    return {"status": _status_for(latency), "latency_ms": latency, "message": f"{tls}, bind and base DN OK ({target.get('bind_dn')})"}


def _ldap_passwords(targets: list[dict]) -> dict[str, str]:
    refs = sorted({str(t.get("secret_ref")) for t in targets if str(t.get("kind") or "").lower() == "ldap" and t.get("secret_ref")})
    if not refs:
        return {}
    from app.services.secret_broker_client import resolve_secret_refs

    # One by one: a wrong reference of one source must not hide the password of the others
    passwords: dict[str, str] = {}
    for ref in refs:
        try:
            passwords.update(resolve_secret_refs([ref]) or {})
        except Exception:
            pass  # that directory then reports that its password could not be read
    return passwords


def run_infra_health_check(params: dict):
    targets = [t for t in (params.get("targets") or []) if isinstance(t, dict) and t.get("component")]
    timeout = max(1, min(int(params.get("timeout") or 5), 15))
    verify_tls = bool(params.get("verify_tls", True))

    passwords = _ldap_passwords(targets)

    def _one(target: dict) -> dict:
        kind = str(target.get("kind") or "http").lower()
        value = str(target.get("target") or "")
        if kind == "ldap":
            result = check_ldap(target, passwords.get(str(target.get("secret_ref") or "")), timeout)
        elif kind == "tcp":
            result = check_tcp(value, timeout)
        else:
            result = check_http(value, timeout, verify_tls)
        return {"component": target["component"], "kind": kind, "target": value, **result}

    with ThreadPoolExecutor(max_workers=min(16, max(1, len(targets)))) as pool:
        results = list(pool.map(_one, targets))

    down = [r["component"] for r in results if r["status"] == "down"]
    message = f"{len(results) - len(down)}/{len(results)} components reachable"
    # The check itself succeeded even when components are down: the results carry the states
    return True, message, {"results": results, "checked_by": socket.gethostname(), "down": down}
