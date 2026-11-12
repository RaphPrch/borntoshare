"""A server that does not answer is left alone for a while instead of being asked again and again.

Read from the jobs themselves (no state of its own): the last jobs on a server, newest first. After TRIP_AFTER
connection failures in a row the server is « down »: the automatic tasks on it are refused until a retry time that
doubles at each new failure (5 min, 10, 20, 40, then every hour). At the retry time one job goes through (the next
one asked); its success closes everything. One alert per server while it is down, resolved by the first success.

The test button of an administrator always goes through: after fixing a server, one checks it at once.
"""
from __future__ import annotations

import ipaddress
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

TRIP_AFTER = 3
BASE_MINUTES = 5
MAX_MINUTES = 60
# Explicit checks by an administrator are never refused
EXEMPT_ORIGINS = {"admin", "wizard"}
# The worker's own codes for « the server did not answer » (LDAP, WinRM, SMB)
CONNECTION_CODES = {"AD_UNREACHABLE", "LDAP_UNREACHABLE", "WINRM_UNREACHABLE", "WINRM_TIMEOUT", "WINRM_KERBEROS_TIMEOUT",
                    "DISCOVERY_UNREACHABLE", "SMB_UNREACHABLE"}
# The server did not answer at all (as opposed to a refused password or a missing folder)
CONNECTION_ERROR = re.compile(
    r"NT_STATUS_(CONNECTION_REFUSED|HOST_UNREACHABLE|NETWORK_UNREACHABLE|IO_TIMEOUT|CONNECTION_RESET|CONNECTION_DISCONNECTED)"
    r"|do_connect: Connection to .* failed|Connection refused|No route to host|Errno (111|113|110)|timed out",
    re.IGNORECASE,
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def host_key(host: Any) -> str:
    """DFS01, dfs01 and DFS01.corp.local are the same server; an IP address stays whole."""
    value = str(host or "").strip().strip("\\/").lower()
    if not value:
        return ""
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        return value.split(".", 1)[0]


def host_of_payload(payload_json: Any) -> str:
    data = payload_json
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return ""
    inner = ((data or {}).get("payload") or {}) if isinstance(data, dict) else {}
    target = inner.get("target") or {}
    # Probes carry the server in target.host; directory jobs (snapshot, groups, members) in payload.host
    return host_key((target.get("host") if isinstance(target, dict) else None) or inner.get("host"))


def is_connection_error(message: Any, code: Any = None) -> bool:
    return str(code or "").upper() in CONNECTION_CODES or bool(CONNECTION_ERROR.search(str(message or "")))


def backoff_minutes(failures: int) -> int:
    return min(MAX_MINUTES, BASE_MINUTES * 2 ** max(0, failures - TRIP_AFTER))


def evaluate(history: list[tuple], now: datetime) -> dict[str, Any]:
    """history: (status, error message, finished at[, error code]) of the last finished jobs on the server, newest first."""
    failures, first, last = 0, None, None
    for state, error, finished, *rest in history:
        if str(state).upper() != "FAILED" or not is_connection_error(error, rest[0] if rest else None):
            break
        failures += 1
        last = last or finished
        first = finished
    down = failures >= TRIP_AFTER
    retry_at = (last + timedelta(minutes=backoff_minutes(failures))) if down and last else None
    return {"down": down, "failures": failures, "since": first if down else None, "last": last if down else None,
            "retry_at": retry_at, "waiting": bool(down and retry_at and now < retry_at)}


def _rows(db: Session, key: str, sql_status: str, limit: int) -> list[Any]:
    return db.execute(
        text(f"""
            SELECT status, error_message, finished_at, created_at, error_code FROM provisioning_jobs
            WHERE created_at > :since AND status IN ({sql_status})
              AND (LOWER(COALESCE(JSON_VALUE(payload_json, '$.payload.target.host'), JSON_VALUE(payload_json, '$.payload.host'))) = :key
                   OR LOWER(COALESCE(JSON_VALUE(payload_json, '$.payload.target.host'), JSON_VALUE(payload_json, '$.payload.host'))) LIKE :like)
            ORDER BY COALESCE(finished_at, created_at) DESC LIMIT {int(limit)}"""),
        {"since": _now() - timedelta(days=1), "key": key, "like": f"{key}.%" if not _is_ip(key) else key},
    ).all()


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def state(db: Session, host: Any) -> dict[str, Any]:
    key = host_key(host)
    if not key:
        return {"down": False, "failures": 0}
    try:
        rows = _rows(db, key, "'SUCCEEDED', 'FAILED'", 12)
    except Exception:
        db.rollback()
        return {"down": False, "failures": 0}
    return {"host": key, **evaluate([(row[0], row[1], row[2] or row[3], row[4]) for row in rows], _now())}


def guard(db: Session, host: Any, origin: Any = None) -> None:
    """Refuses a job on a server that is down, until its retry time; then lets one through at a time."""
    if str(origin or "") in EXEMPT_ORIGINS:
        return
    current = state(db, host)
    if not current.get("down"):
        return
    when = current["retry_at"].strftime("%H:%M") if current.get("retry_at") else "?"
    if not current["waiting"]:
        # Retry time passed: one job tries; the others wait for its answer
        try:
            active = _rows(db, current["host"], "'QUEUED', 'RUNNING'", 1)
        except Exception:
            db.rollback()
            active = []
        if not active:
            return
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"error_code": "SERVER_UNREACHABLE",
                "message": f"Le serveur {current['host']} ne répond plus ({current['failures']} échecs de connexion de suite) : "
                           f"nouvel essai automatique vers {when} UTC. Un administrateur peut le tester tout de suite."},
    )


def after_job(db: Session, payload_json: Any) -> None:
    """After a job on a server: an alert while it is down, resolved by its first success."""
    from app.data.repositories.governance_alerts_repo import GovernanceAlertsRepo

    key = host_of_payload(payload_json)
    if not key:
        return
    alert_key = f"server_unreachable:{key}"
    try:
        current = state(db, key)
        if not current.get("down"):
            if current.get("failures", 0) == 0:
                db.execute(text("UPDATE governance_alerts SET status = 'resolved', resolved_at = :now WHERE alert_key = :key AND status <> 'resolved'"),
                           {"now": _now(), "key": alert_key})
                db.commit()
            return
        already = db.execute(text("SELECT 1 FROM governance_alerts WHERE alert_key = :key AND status <> 'resolved' LIMIT 1"),
                             {"key": alert_key}).first()
        since = current["since"].strftime("%d/%m %H:%M") if current.get("since") else "?"
        retry = current["retry_at"].strftime("%H:%M") if current.get("retry_at") else "?"
        endpoint = db.execute(text("""SELECT id, zone_id FROM storage_endpoints WHERE deleted_at IS NULL
                                        AND (LOWER(host) = :key OR LOWER(host) LIKE :like OR LOWER(name) = :key) ORDER BY id LIMIT 1"""),
                              {"key": key, "like": f"{key}.%" if not _is_ip(key) else key}).first()
        GovernanceAlertsRepo(db)._upsert_alert({
            "alert_key": alert_key, "scope_type": "storage_endpoint", "scope_id": int(endpoint[0]) if endpoint else 0,
            "storage_endpoint_id": int(endpoint[0]) if endpoint else None, "zone_id": endpoint[1] if endpoint else None,
            "alert_type": "server_unreachable",
            "severity": "high", "title": f"Serveur {key} injoignable",
            "message": (f"{current['failures']} échecs de connexion de suite depuis le {since} UTC. Les tâches automatiques sur ce serveur "
                        f"sont suspendues ; prochain essai vers {retry} UTC."),
            "source_type": "server", "source_id": key, "metadata_json": {"host": key, "failures": current["failures"]},
        })
        db.commit()
        if not already:
            from app.services import notifications

            notifications.admin_alert(
                db, f"server_unreachable:{key}:{current['since']:%Y%m%d%H%M}" if current.get("since") else f"server_unreachable:{key}",
                f"Serveur {key} injoignable",
                [f"{current['failures']} échecs de connexion de suite depuis le {since} UTC.",
                 f"Tâches automatiques suspendues ; prochain essai vers {retry} UTC."],
                "/observability?tab=alerts",
                intro="BornToShare n'arrive plus à joindre ce serveur. Les tâches automatiques qui le visent attendent son retour.")
    except Exception:
        db.rollback()
