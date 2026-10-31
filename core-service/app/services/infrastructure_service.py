"""Advanced Settings › Infrastructure: database, workers, monitored components and their state.

Health check, in two halves:
- core-service checks what only it can see: its database connections, the job queue, each worker
  through its agent (a worker cannot report that it is down);
- one worker checks the rest from its network position (job INFRA_HEALTH): web and API services,
  the database port, domain controllers, file servers, Keycloak.
Results land in infra_component_status (last state) and infra_check_history (availability bars).
"""
from __future__ import annotations

import asyncio
import json
import hashlib
import hmac
import os
import ssl
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.runtime_config import (
    build_url,
    parse_dsn,
    read_database_config,
    runtime_dir,
    runtime_dir_writable,
    write_database_config,
)

# Tables a BornToShare database must have before core-service is pointed at it
REQUIRED_TABLES = ("identity_sources", "identities", "roles", "storage_endpoints", "storage_roots", "access_requests", "infra_schedules")
HISTORY_DAYS = 7
SLOW_MS = 1500


def _now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat() + "Z"
    return str(value) if value else None


def _json(value: Any) -> Any:
    if isinstance(value, (bytes, str)) and value:
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


# ============================================================
# Database
# ============================================================


def database_info() -> dict[str, Any]:
    """Running connection (no password) and the one saved for the next start, if different."""
    settings = get_settings()
    running = {
        "source": settings.DB_CONFIG_SOURCE,
        "mode": "dsn" if settings.DATABASE_URL_OVERRIDE else "fields",
        "host": settings.DB_HOST,
        "port": int(settings.DB_PORT),
        "name": settings.DB_NAME,
        "user": settings.DB_USER,
        "logging_name": settings.LOGGING_DB_NAME,
    }
    saved = read_database_config()
    configured = None
    if saved:
        if saved["mode"] == "dsn":
            parts = parse_dsn(saved.get("dsn") or "")
            configured = {"mode": "dsn", **{k: parts[k] for k in ("host", "port", "name", "user")}, "has_password": parts["has_password"]}
        else:
            configured = {
                "mode": "fields",
                "host": saved.get("host"),
                "port": int(saved.get("port") or 3306),
                "name": saved.get("name"),
                "user": saved.get("user"),
                "logging_name": saved.get("logging_name"),
                "has_password": bool(saved.get("password")),
            }
        configured.update(updated_at=saved.get("updated_at"), updated_by=saved.get("updated_by"))
    pending = bool(
        configured
        and any(str(configured.get(k)) != str(running.get(k)) for k in ("host", "port", "name", "user"))
    ) or (configured is None and running["source"] == "runtime")  # back to .env at the next start
    return {
        "running": running,
        "configured": configured,
        "pending_restart": pending,
        "runtime_dir": str(runtime_dir()),
        "runtime_dir_writable": runtime_dir_writable(),
    }


def _url_from_request(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """SQLAlchemy URL and the file content to save, from the form (password may be omitted to keep it)."""
    settings = get_settings()
    if payload.get("mode") == "dsn":
        dsn = str(payload.get("dsn") or "").strip()
        parse_dsn(dsn)
        return dsn, {"mode": "dsn", "dsn": dsn, "logging_dsn": str(payload.get("logging_dsn") or "").strip() or None}

    host = str(payload.get("host") or "").strip()
    name = str(payload.get("name") or "").strip()
    user = str(payload.get("user") or "").strip()
    port = int(payload.get("port") or 3306)
    if not host or not name or not user:
        raise ValueError("Server, database and user are required")
    password = str(payload.get("password") or "")
    if not password:
        # Kept: the saved one, else the running one when the server and account are unchanged
        saved = read_database_config() or {}
        if saved.get("mode") == "fields" and saved.get("host") == host and saved.get("user") == user:
            password = str(saved.get("password") or "")
        elif host == settings.DB_HOST and user == settings.DB_USER:
            password = settings.DB_PASSWORD
    if not password:
        raise ValueError("The password of the database account is required")
    url = build_url(driver=settings.DB_DRIVER, host=host, port=port, name=name, user=user, password=password)
    logging_name = str(payload.get("logging_name") or "").strip() or settings.LOGGING_DB_NAME
    return url, {"mode": "fields", "host": host, "port": port, "name": name, "user": user, "password": password, "logging_name": logging_name}


def test_database(payload: dict[str, Any]) -> dict[str, Any]:
    """Connect with the proposed settings: server version, latency, BornToShare schema present."""
    try:
        url, _config = _url_from_request(payload)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    started = time.monotonic()
    engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT VERSION()")).scalar()
            latency = int((time.monotonic() - started) * 1000)
            present = {
                str(row[0]).lower()
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()")
                )
            }
    except Exception as exc:
        message = str(getattr(exc, "orig", exc))
        return {"ok": False, "message": f"Connection failed: {message[:300]}"}
    finally:
        engine.dispose()
    missing = [t for t in REQUIRED_TABLES if t not in present]
    return {
        "ok": not missing,
        "latency_ms": latency,
        "version": str(version or ""),
        "tables": len(present),
        "missing_tables": missing,
        "message": "Connection OK, BornToShare schema present"
        if not missing
        else "Connected, but the BornToShare schema is not up to date (apply the migrations)"
        if len(missing) < len(REQUIRED_TABLES) // 2
        else "Connected, but this database does not hold the BornToShare schema (run the installation wizard first)",
    }


def save_database(payload: dict[str, Any], actor_display: str | None) -> dict[str, Any]:
    """Tested again on the server before writing: a wrong database would stop the platform at restart."""
    if not runtime_dir_writable():
        raise PermissionError(f"The runtime directory {runtime_dir()} is not writable (mount it read-write)")
    result = test_database(payload)
    if not result.get("ok"):
        raise ValueError(result.get("message") or "Database test failed")
    _url, config = _url_from_request(payload)
    config.update(updated_at=_iso(_now()), updated_by=actor_display)
    write_database_config(config)
    return {**database_info(), "test": result}


def reset_database() -> dict[str, Any]:
    """Back to the .env settings at the next start."""
    from app.core.runtime_config import database_file

    try:
        database_file().unlink()
    except FileNotFoundError:
        pass
    return database_info()


# ============================================================
# Workers (agent API)
# ============================================================

WORKER_PUBLIC_FIELDS = (
    "id", "name", "host", "port", "use_tls", "verify_tls", "is_enabled", "status",
    "last_check_at", "last_seen_at", "last_message", "version", "hostname", "max_scope", "details_json",
)


def _worker_public(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k) for k in WORKER_PUBLIC_FIELDS}
    out["use_tls"] = bool(out["use_tls"])
    out["verify_tls"] = bool(out["verify_tls"])
    out["is_enabled"] = bool(out["is_enabled"])
    out["details"] = _json(out.pop("details_json")) or {}
    out["has_password"] = bool(row.get("password_ref"))
    out["agent_url"] = agent_url(row)
    for key in ("last_check_at", "last_seen_at"):
        out[key] = _iso(out[key])
    return out


def agent_url(row: dict[str, Any]) -> str:
    scheme = "https" if bool(row.get("use_tls")) else "http"
    host = str(row.get("host") or "")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{scheme}://{host}:{int(row.get('port') or 8443)}"


def list_workers(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(text("SELECT * FROM infra_workers ORDER BY name")).mappings().all()
    return [_worker_public(dict(r)) for r in rows]


def get_worker_row(db: Session, worker_id: int) -> dict[str, Any] | None:
    row = db.execute(text("SELECT * FROM infra_workers WHERE id = :id"), {"id": int(worker_id)}).mappings().first()
    return dict(row) if row else None


def agent_token() -> str:
    """Proof shown to the agent of a worker, derived from INTERNAL_TOKEN: a host that receives it learns nothing of that token."""
    return hmac.new((os.getenv("INTERNAL_TOKEN") or "").encode(), b"b2s-agent", hashlib.sha256).hexdigest()


async def check_agent(row: dict[str, Any]) -> dict[str, Any]:
    """Call the agent of a worker: healthy (agent + Dramatiq + queue OK), degraded, or down with the reason."""
    url = f"{agent_url(row)}/agent/v1/info"
    # Certificate of the agent: system authorities, plus the private CA of B2S_AGENT_CA_FILE when set
    ca_file = (os.getenv("B2S_AGENT_CA_FILE") or "").strip()
    verify: Any = bool(row.get("verify_tls", True))
    if verify and ca_file and os.path.isfile(ca_file):
        verify = ssl.create_default_context(cafile=ca_file)
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=6.0, verify=verify) as client:
            resp = await client.get(url, headers={"X-Agent-Token": agent_token()})
    except httpx.ConnectError as exc:
        text_exc = str(exc).lower()
        if "certificate" in text_exc or "ssl" in text_exc:
            return {"status": "down", "message": "Certificate of the agent refused (uncheck “Verify certificate” for a self-signed one)", "latency_ms": None, "details": {}}
        return {"status": "down", "message": f"Agent unreachable at {url}: check the host, the port and the firewall", "latency_ms": None, "details": {}}
    except httpx.TimeoutException:
        return {"status": "down", "message": f"No answer from {url} (timeout): check the host, the port and the firewall", "latency_ms": None, "details": {}}
    except httpx.RemoteProtocolError:
        hint = "the agent uses HTTPS: enable TLS" if not row.get("use_tls") else "the agent does not speak HTTPS: disable TLS or set AGENT_TLS_CERT on the worker"
        return {"status": "down", "message": f"The agent closed the connection ({hint})", "latency_ms": None, "details": {}}
    except httpx.HTTPError as exc:
        return {"status": "down", "message": str(exc)[:300], "latency_ms": None, "details": {}}
    latency = int((time.monotonic() - started) * 1000)
    if resp.status_code == 401:
        return {"status": "down", "message": "The agent refused this server: INTERNAL_TOKEN differs on the worker", "latency_ms": latency, "details": {}}
    if resp.status_code != 200:
        return {"status": "down", "message": f"Agent answered HTTP {resp.status_code}", "latency_ms": latency, "details": {}}
    body = resp.json() if resp.content else {}
    info = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else body
    problems = []
    if int(info.get("worker_processes") or 0) == 0:
        problems.append("no job process running")
    if not (info.get("broker") or {}).get("reachable"):
        problems.append("job queue unreachable")
    status = "degraded" if problems or latency > SLOW_MS else "healthy"
    message = "; ".join(problems) if problems else f"Agent OK · {info.get('hostname')} · {latency} ms"
    return {"status": status, "message": message, "latency_ms": latency, "details": info}


def record_worker_check(db: Session, worker_id: int, result: dict[str, Any]) -> None:
    info = result.get("details") or {}
    now = _now()
    db.execute(
        text(
            """
            UPDATE infra_workers
            SET status = :status, last_check_at = :now, last_message = :message,
                last_seen_at = CASE WHEN :status IN ('healthy', 'degraded') THEN :now ELSE last_seen_at END,
                version = COALESCE(:version, version), hostname = COALESCE(:hostname, hostname),
                max_scope = COALESCE(:max_scope, max_scope), details_json = :details
            WHERE id = :id
            """
        ),
        {
            "id": int(worker_id),
            "status": result.get("status") if result.get("status") in {"healthy", "degraded", "down"} else "unknown",
            "now": now,
            "message": str(result.get("message") or "")[:512],
            "version": info.get("version"),
            "hostname": info.get("hostname"),
            "max_scope": info.get("max_scope"),
            "details": json.dumps(info) if info else None,
        },
    )


# ============================================================
# Component states
# ============================================================


def record_components(db: Session, results: list[dict[str, Any]], *, checked_by: str) -> None:
    now = _now()
    for item in results:
        status = item.get("status") if item.get("status") in {"healthy", "degraded", "down", "unknown"} else "unknown"
        params = {
            "component": str(item["component"])[:96],
            "label": str(item.get("label") or item["component"])[:190],
            "category": str(item.get("category") or "service")[:32],
            "status": status,
            "latency": item.get("latency_ms"),
            "message": str(item.get("message") or "")[:512],
            "checked_by": str(item.get("checked_by") or checked_by)[:120],
            "details": json.dumps(item.get("details")) if item.get("details") else None,
            "now": now,
        }
        db.execute(
            text(
                """
                INSERT INTO infra_component_status
                  (component, label, category, status, latency_ms, message, checked_by, details_json, checked_at)
                VALUES (:component, :label, :category, :status, :latency, :message, :checked_by, :details, :now)
                ON DUPLICATE KEY UPDATE label = VALUES(label), category = VALUES(category), status = VALUES(status),
                  latency_ms = VALUES(latency_ms), message = VALUES(message), checked_by = VALUES(checked_by),
                  details_json = VALUES(details_json), checked_at = VALUES(checked_at)
                """
            ),
            params,
        )
        db.execute(
            text(
                "INSERT INTO infra_check_history (component, status, latency_ms, checked_at) VALUES (:component, :status, :latency, :now)"
            ),
            params,
        )
    db.execute(
        text("DELETE FROM infra_check_history WHERE checked_at < :limit"),
        {"limit": now - timedelta(days=HISTORY_DAYS)},
    )


def _core_side_checks() -> list[dict[str, Any]]:
    """What only core-service sees: its two database connections and the job queue."""
    from app.core.db import engine
    from app.core.logging_db import logging_engine

    settings = get_settings()
    out: list[dict[str, Any]] = []
    for component, label, eng, target in (
        ("database", "Database", engine, f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"),
        ("logging_database", "Audit database", logging_engine, f"{settings.LOGGING_DB_HOST}:{settings.LOGGING_DB_PORT}/{settings.LOGGING_DB_NAME}"),
    ):
        started = time.monotonic()
        try:
            with eng.connect() as conn:
                version = conn.execute(text("SELECT VERSION()")).scalar()
            latency = int((time.monotonic() - started) * 1000)
            out.append({
                "component": component, "label": label, "category": "data",
                "status": "degraded" if latency > SLOW_MS else "healthy", "latency_ms": latency,
                "message": f"{target} · {version}", "details": {"target": target, "version": str(version)},
            })
        except Exception as exc:
            out.append({
                "component": component, "label": label, "category": "data", "status": "down", "latency_ms": None,
                "message": f"{target}: {str(getattr(exc, 'orig', exc))[:250]}", "details": {"target": target},
            })

    started = time.monotonic()
    try:
        from redis import Redis

        Redis.from_url(settings.CAPSULE_BROKER_URL, socket_timeout=3, socket_connect_timeout=3).ping()
        latency = int((time.monotonic() - started) * 1000)
        out.append({"component": "job_queue", "label": "Job queue", "category": "queue", "status": "healthy", "latency_ms": latency, "message": "Redis answers"})
    except Exception as exc:
        out.append({"component": "job_queue", "label": "Job queue", "category": "queue", "status": "down", "latency_ms": None, "message": str(exc)[:250]})
    return out


def worker_targets(db: Session) -> list[dict[str, Any]]:
    """Components checked from a worker: platform services, database port, directories, file servers, Keycloak."""
    settings = get_settings()
    targets: list[dict[str, Any]] = []
    for row in db.execute(text("SELECT * FROM infra_services WHERE is_enabled = 1 ORDER BY id")).mappings():
        targets.append({"component": f"service:{row['component_key']}", "label": row["label"], "category": row["category"], "kind": row["check_kind"], "target": row["target"]})
    targets.append({"component": "database_network", "label": "Database server (from the worker)", "category": "data", "kind": "tcp", "target": f"{settings.DB_HOST}:{settings.DB_PORT}"})
    from app.services.identity_source_accounts import load_accounts

    for row in db.execute(
        text(
            """
            SELECT id, name, host, port, protocol, base_dn, bind_dn, bind_password_ref, tls_verify, tls_ca_pem, tls_server_name
            FROM identity_sources WHERE is_active = 1 AND LOWER(type) = 'ad' AND host IS NOT NULL
            """
        )
    ).mappings():
        use_ssl = str(row["protocol"] or "").lower() != "ldap"
        port = int(row["port"] or (636 if use_ssl else 389))
        # A real LDAP check (TLS, bind with the account that reads the directory, base DN), not only the port
        account = load_accounts(db, int(row["id"])).get("snapshot") or {}
        bind_dn = account.get("bind_dn") or row["bind_dn"]
        secret_ref = account.get("bind_password_ref") or row["bind_password_ref"]
        target = {"component": f"identity_source:{row['id']}", "label": f"Directory · {row['name']}", "category": "directory", "target": f"{row['host']}:{port}"}
        if bind_dn and secret_ref:
            target.update({"kind": "ldap", "use_ssl": use_ssl, "verify_tls": bool(row["tls_verify"]), "tls_ca_pem": row["tls_ca_pem"], "tls_server_name": row["tls_server_name"], "base_dn": row["base_dn"], "bind_dn": bind_dn, "secret_ref": secret_ref})
        else:
            target["kind"] = "tcp"
        targets.append(target)
    for row in db.execute(
        text("SELECT id, name, host, port FROM storage_endpoints WHERE host IS NOT NULL AND host <> ''")
    ).mappings():
        targets.append({"component": f"storage_endpoint:{row['id']}", "label": f"File server · {row['name']}", "category": "storage", "kind": "tcp", "target": f"{row['host']}:{int(row['port'] or 445)}"})
    try:
        for row in db.execute(text("SELECT id, name, base_url, realm FROM sso_providers WHERE is_enabled = 1")).mappings():
            discovery = f"{str(row['base_url']).rstrip('/')}/realms/{row['realm']}/.well-known/openid-configuration"
            targets.append({"component": f"sso:{row['id']}", "label": f"Keycloak · {row['name']}", "category": "security", "kind": "http", "target": discovery})
    except Exception:
        db.rollback()  # sso_providers not migrated yet
    return targets


async def run_health_check(db: Session, *, trigger: str) -> dict[str, Any]:
    """Core-side checks now, worker agents now, the rest queued to a worker (results on job completion)."""
    from app.services.provisioning_jobs import create_and_publish_job

    results = _core_side_checks()

    workers = [dict(r) for r in db.execute(text("SELECT * FROM infra_workers WHERE is_enabled = 1")).mappings()]
    checks = await asyncio.gather(*(check_agent(w) for w in workers))
    for worker, check in zip(workers, checks):
        record_worker_check(db, int(worker["id"]), check)
        results.append({
            "component": f"worker:{worker['id']}", "label": f"Worker · {worker['name']}", "category": "worker",
            "status": check["status"], "latency_ms": check.get("latency_ms"), "message": check.get("message"),
        })
    record_components(db, results, checked_by="core-service")
    db.commit()

    targets = worker_targets(db)
    job_id = None
    queued_error = None
    try:
        created = await create_and_publish_job(
            payload={
                "correlation_id": f"infrahealth_{uuid.uuid4().hex}",
                "job_type": "INFRA_HEALTH",
                "action": "infra_health_check",
                "status": "QUEUED",
                "payload_json": {
                    "action": "infra_health_check",
                    "payload": {"targets": targets, "timeout": 5, "verify_tls": False, "trigger": trigger},
                },
            }
        )
        job_id = created.get("job_id")
    except Exception as exc:
        queued_error = str(exc)[:300]

    down = [r for r in results if r["status"] == "down"]
    return {
        "core_checks": len(results),
        "core_down": len(down),
        "worker_job_id": job_id,
        "worker_targets": len(targets),
        "queued_error": queued_error,
    }


def apply_worker_health_results(db: Session, *, job_payload: dict[str, Any], result_json: dict[str, Any]) -> None:
    """Job INFRA_HEALTH completed: store each component with the label and category of its target."""
    payload = (job_payload or {}).get("payload") or job_payload or {}
    by_component = {t.get("component"): t for t in (payload.get("targets") or []) if isinstance(t, dict)}
    details = (result_json or {}).get("details") or {}
    checked_by = f"worker {details.get('checked_by') or ''}".strip()
    results = []
    for item in details.get("results") or []:
        target = by_component.get(item.get("component")) or {}
        results.append({
            **item,
            "label": target.get("label") or item.get("component"),
            "category": target.get("category") or "service",
            "details": {"target": item.get("target"), "kind": item.get("kind")},
        })
    record_components(db, results, checked_by=checked_by)


# ============================================================
# Overview
# ============================================================


def overview(db: Session) -> dict[str, Any]:
    rows = [dict(r) for r in db.execute(text("SELECT * FROM infra_component_status ORDER BY category, label")).mappings()]
    since = _now() - timedelta(hours=24)
    history: dict[str, list[dict[str, Any]]] = {}
    for h in db.execute(
        text("SELECT component, status, latency_ms, checked_at FROM infra_check_history WHERE checked_at >= :since ORDER BY checked_at"),
        {"since": since},
    ).mappings():
        history.setdefault(h["component"], []).append({"status": h["status"], "latency_ms": h["latency_ms"], "at": _iso(h["checked_at"])})

    schedule = db.execute(text("SELECT interval_minutes FROM infra_schedules WHERE task = 'health_check'")).scalar()
    stale_after = timedelta(minutes=max(15, int(schedule or 5) * 3))
    components = []
    for row in rows:
        points = history.get(row["component"], [])
        up = sum(1 for p in points if p["status"] in {"healthy", "degraded"})
        stale = row["checked_at"] < _now() - stale_after
        components.append({
            "component": row["component"],
            "label": row["label"],
            "category": row["category"],
            "status": "unknown" if stale else row["status"],
            "stale": stale,
            "latency_ms": row["latency_ms"],
            "message": row["message"],
            "checked_by": row["checked_by"],
            "checked_at": _iso(row["checked_at"]),
            "details": _json(row["details_json"]) or {},
            "uptime_24h": round(100.0 * up / len(points), 1) if points else None,
            "history": points[-48:],
        })
    summary = {s: sum(1 for c in components if c["status"] == s) for s in ("healthy", "degraded", "down", "unknown")}
    return {"components": components, "summary": {**summary, "total": len(components)}, "generated_at": _iso(_now())}
