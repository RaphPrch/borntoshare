"""The scanner of the 5S module: takes the scans of the queue (b2s_fives.scan_runs) and walks the folders ON their
Windows file server, without agent (WinRM, Kerberos).

For each scan:
1. the folder and its account (core), the password (secret broker of the core), its pieces (first-level sub-folders);
2. full walk, or incremental: only the pieces where the NTFS change journal (USN) shows a change since the last scan
   (a new journal, a journal that lost the changes, or `full_every_days` reached: full walk);
3. each piece walked is saved at once (scan_chunks): a scan stopped halfway resumes at the next piece;
4. the folder = the sum of its pieces → history and fingerprints (module), content and state (core, folder page).
A server that cannot be walked on is measured by the worker of the core through SMB (« delegated »).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from scanner import config, core
from scanner.chunk import ScanError, full_scan, list_chunks, walk_chunks
from scanner.db import InventorySession, Session
from scanner.merge import chunk_of, merge

logger = logging.getLogger("fives.scanner")
DEFAULT_SETTINGS = {"schedule_enabled": True, "window_start": "20:00", "window_end": "06:00", "timezone": "Europe/Paris",
                    "per_server": 1, "interval_days": 7, "full_every_days": 30, "hash_files_max": 20000}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def settings(db) -> dict[str, Any]:
    row = db.execute(text("SELECT value_json FROM module_settings WHERE setting_key = 'scanner'")).first()
    return {**DEFAULT_SETTINGS, **(json.loads(row[0]) if row and row[0] else {})}


def in_window(values: dict[str, Any], now_utc: datetime | None = None) -> bool:
    from datetime import time as clock
    from zoneinfo import ZoneInfo

    local = (now_utc or _now()).replace(tzinfo=timezone.utc).astimezone(ZoneInfo(str(values.get("timezone") or "Europe/Paris")))
    start, end = clock.fromisoformat(values["window_start"]), clock.fromisoformat(values["window_end"])
    current = local.time().replace(second=0, microsecond=0)
    return start <= current < end if start < end else (current >= start or current < end)


def claim(db) -> dict[str, Any] | None:
    """The oldest runnable scan: asked by a person at once, scheduled ones inside the window; servers at capacity skipped.
    One claim at a time for every scanner (lock of the database): the limit per server is never passed."""
    if not db.execute(text("SELECT GET_LOCK('b2s_fives_claim', 10)")).scalar():
        db.rollback()
        return None
    try:
        return _claim(db)
    finally:
        db.execute(text("SELECT RELEASE_LOCK('b2s_fives_claim')"))


def _claim(db) -> dict[str, Any] | None:
    values = settings(db)
    reasons = ("manual", "policy", "schedule") if in_window(values) else ("manual", "policy")
    row = db.execute(
        text(
            f"""
            SELECT * FROM scan_runs WHERE status = 'queued' AND reason IN ({", ".join(f"'{r}'" for r in reasons)})
              AND host NOT IN (SELECT host FROM (SELECT host FROM scan_runs WHERE status = 'running' GROUP BY host HAVING COUNT(*) >= :limit) busy)
            ORDER BY FIELD(reason, 'manual', 'policy', 'schedule'), requested_at LIMIT 1 FOR UPDATE SKIP LOCKED
            """
        ),
        {"limit": int(values["per_server"])},
    ).mappings().first()
    if not row:
        db.rollback()
        return None
    db.execute(text("""UPDATE scan_runs SET status = 'running', started_at = COALESCE(started_at, :now), heartbeat_at = :now,
                       scanner_id = :me, attempts = attempts + 1 WHERE id = :id"""), {"id": row["id"], "now": _now(), "me": config.SCANNER_ID})
    db.commit()
    return {**dict(row), "settings": values}


def _progress(run_id: int, root_id: int, progress: dict[str, Any]) -> None:
    with Session() as db:
        db.execute(text("UPDATE scan_runs SET heartbeat_at = :now, progress_json = :p WHERE id = :id"),
                   {"id": run_id, "now": _now(), "p": json.dumps(progress)})
        db.commit()
    try:
        core.report(root_id, status="running", progress=progress)
    except Exception:
        logger.warning("Progress not sent to the core", exc_info=True)


def _finish(run_id: int, status: str, *, mode: str | None = None, summary: dict | None = None, error: str | None = None) -> None:
    with Session() as db:
        db.execute(text("""UPDATE scan_runs SET status = :s, finished_at = :now, heartbeat_at = :now, mode = COALESCE(:mode, mode),
                           summary_json = :summary, error_message = :error WHERE id = :id"""),
                   {"id": run_id, "s": status, "now": _now(), "mode": mode, "summary": json.dumps(summary) if summary else None,
                    "error": (error or None) and error[:600]})
        db.commit()


def _connection(ctx: dict[str, Any]) -> dict[str, Any]:
    return {"host": ctx["host"], "server_name": ctx.get("server_name"), "username": ctx["username"], "password": core.password(ctx["secret_ref"]),
            "domain": ctx.get("domain") or "", "kdc_hint": ctx.get("kdc_host")}


def plan(*, chunks: list[str], known: set[str], state: dict[str, Any] | None, journal: dict[str, Any] | None, local: str,
         full_due: bool) -> tuple[str, set[str]]:
    """Which pieces to walk: (« full » | « incremental », keys). New pieces are always walked."""
    current = {"", *chunks}
    if full_due or not state or not journal or journal.get("changed") is None or not known:
        return "full", current
    changed = {chunk_of(path, local) for path in journal["changed"]}
    changed.discard(None)
    return "incremental", {key for key in current if key in changed or key not in known}


def scan(run: dict[str, Any]) -> None:
    from app.actions.smb import _JUNK
    from app.shared.winrm import WinRMError

    run_id, root_id, values = int(run["id"]), int(run["storage_root_id"]), run["settings"]
    started = time.monotonic()
    ctx = core.context(root_id)
    if not ctx.get("server_name"):
        core.delegate(root_id, "no Windows server to walk on (DFS namespace or non Windows server)")
        _finish(run_id, "delegated", error="Measured by the worker of the core through SMB: no Windows server to walk on")
        return
    with Session() as db:
        state = db.execute(text("SELECT * FROM scan_state WHERE storage_root_id = :id"), {"id": root_id}).mappings().first()
        state = dict(state) if state else None
        known = {row[0] for row in db.execute(text("SELECT chunk_key FROM scan_chunks WHERE storage_root_id = :id"), {"id": root_id}).all()}
    full_due = not state or not state.get("last_full_at") or state["last_full_at"] < _now() - timedelta(days=int(values["full_every_days"]))
    # Full walk (first scan, or due): the pieces, the journal position and the walk in one session; else the pieces
    # and the changes of the journal first, then only the pieces that changed
    full_upfront = bool(full_due or not known)
    try:
        connection = _connection(ctx)
        if full_upfront:
            listing = full_scan(share=ctx["share"], path=ctx["path"], connection=connection, junk_pattern=_JUNK.pattern,
                                hash_files_max=int(values["hash_files_max"]))
        else:
            listing = list_chunks(share=ctx["share"], path=ctx["path"], connection=connection,
                                  since_usn=(state or {}).get("next_usn"), journal_id=(state or {}).get("journal_id"))
    except (WinRMError, ScanError) as exc:
        reason = f"{getattr(exc, 'code', 'WINRM_FAILED')}: {getattr(exc, 'message', str(exc))}"[:300]
        core.delegate(root_id, reason)
        _finish(run_id, "delegated", error=f"Measured through SMB: {reason}")
        return
    local, volume = listing["local_path"], listing["volume"]
    journal = listing.get("journal") if isinstance(listing.get("journal"), dict) and not listing["journal"].get("error") else None
    if journal and state and (state.get("volume") != volume or state.get("local_path") != local):
        journal = {**journal, "changed": None}  # the folder moved: its journal says nothing of the old place
    if full_upfront:
        mode, todo = "full", {"", *listing["chunks"]}
    else:
        mode, todo = plan(chunks=listing["chunks"], known=known, state=state, journal=journal, local=local, full_due=False)
    present = {"", *listing["chunks"]}
    ordered = sorted(todo, key=lambda key: (key != "", key.lower()))
    progress = {"mode": mode, "chunks_total": len(ordered), "chunks_done": 0, "chunks_kept": len(present - todo), "files": 0, "current": None}

    def save(done: list[dict[str, Any]]) -> set[str]:
        with Session() as db:
            for item in done:
                db.execute(text("""INSERT INTO scan_chunks (storage_root_id, chunk_key, stats_json, run_id, scanned_at) VALUES (:id, :k, :s, :run, :now)
                                   ON DUPLICATE KEY UPDATE stats_json = VALUES(stats_json), run_id = VALUES(run_id), scanned_at = VALUES(scanned_at)"""),
                           {"id": root_id, "k": str(item["key"] or ""), "s": json.dumps(item["stats"]), "run": run_id, "now": _now()})
            db.commit()
        progress["chunks_done"] += len(done)
        progress["files"] += sum(int((item.get("stats") or {}).get("files") or 0) for item in done)
        return {str(item["key"] or "") for item in done}

    walked = save(listing.get("walked") or [])
    remaining = [key for key in ordered if key not in walked]
    while remaining:
        # Several pieces per session, within a time budget; each batch is saved at once (a stopped scan resumes here)
        progress["current"] = remaining[0] or "(fichiers du dossier)"
        _progress(run_id, root_id, progress)
        done = walk_chunks(share=ctx["share"], path=ctx["path"], keys=remaining, connection=connection, junk_pattern=_JUNK.pattern,
                           hash_files_max=int(values["hash_files_max"]))
        if not done:
            raise ScanError("SCAN_NO_PIECE", f"The server walked no piece of {local}")
        walked = save(done)
        remaining = [key for key in remaining if key not in walked]
    with Session() as db:
        rows = db.execute(text("SELECT chunk_key, stats_json FROM scan_chunks WHERE storage_root_id = :id"), {"id": root_id}).all()
        chunks = {key: json.loads(value) for key, value in rows if key in present}
        gone = [key for key, _value in rows if key not in present]
        for key in gone:
            db.execute(text("DELETE FROM scan_chunks WHERE storage_root_id = :id AND chunk_key = :k"), {"id": root_id, "k": key})
        stats = merge(chunks, local)
        stats["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        stats["mode"] = mode
        fingerprints = stats.pop("fingerprints")
        now = _now()
        db.execute(text("""INSERT INTO content_history (storage_root_id, measured_at, bytes, files, folders, cold_1y_bytes, cold_3y_bytes, junk_bytes, duplicate_bytes)
                           VALUES (:id, :at, :b, :f, :d, :c1, :c3, :j, :dup)
                           ON DUPLICATE KEY UPDATE bytes = VALUES(bytes), files = VALUES(files), folders = VALUES(folders), cold_1y_bytes = VALUES(cold_1y_bytes),
                             cold_3y_bytes = VALUES(cold_3y_bytes), junk_bytes = VALUES(junk_bytes), duplicate_bytes = VALUES(duplicate_bytes)"""),
                   {"id": root_id, "at": now.replace(minute=0, second=0, microsecond=0), "b": stats["bytes"], "f": stats["files"], "d": stats["folders"],
                    "c1": stats["cold"]["1y"]["bytes"], "c3": stats["cold"]["3y"]["bytes"], "j": stats["junk"]["bytes"], "dup": stats["duplicates"]["wasted_bytes"]})
        # Where the next scan starts: the journal as it was BEFORE this walk (what changed during it is seen next time)
        db.execute(text("""INSERT INTO scan_state (storage_root_id, local_path, volume, journal_id, next_usn, last_full_at, last_done_at)
                           VALUES (:id, :local, :vol, :jid, :usn, :full, :now)
                           ON DUPLICATE KEY UPDATE local_path = VALUES(local_path), volume = VALUES(volume), journal_id = VALUES(journal_id),
                             next_usn = VALUES(next_usn), last_full_at = COALESCE(VALUES(last_full_at), last_full_at), last_done_at = VALUES(last_done_at)"""),
                   {"id": root_id, "local": local, "vol": volume, "jid": (journal or {}).get("journal_id"), "usn": (journal or {}).get("next_usn"),
                    "full": now if mode == "full" else None, "now": now})
        db.commit()
    with InventorySession() as inventory:
        inventory.execute(text("DELETE FROM fingerprints WHERE storage_root_id = :id"), {"id": root_id})
        rows = [{"id": root_id, "fp": str(item["fingerprint"])[:64], "size": int(item.get("size") or 0), "path": str(item.get("path") or "")[:1024],
                 "at": (item.get("modified") or "").replace("T", " ").replace("Z", "")[:19] or None}
                for item in fingerprints if item.get("fingerprint") and item.get("path")]
        if rows:
            inventory.execute(text("INSERT INTO fingerprints (storage_root_id, fingerprint, size_bytes, path, modified_at) VALUES (:id, :fp, :size, :path, :at)"), rows)
        inventory.commit()
    summary = {"mode": mode, "chunks_walked": len(ordered), "chunks_kept": len(present - todo), "files": stats["files"], "bytes": stats["bytes"],
               "elapsed_ms": stats["elapsed_ms"]}
    core.report(root_id, status="done", stats=stats, method="server", elapsed_ms=stats["elapsed_ms"], files=stats["files"], progress=None)
    _finish(run_id, "done", mode=mode, summary=summary)
    logger.info("Scan %s of folder %s: %s", run_id, root_id, summary)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [FIVES-SCANNER] %(name)s - %(message)s")
    logger.info("Scanner %s started", config.SCANNER_ID)
    import threading

    def alive() -> None:
        # Health of the container (podman-compose checks this file is less than 2 minutes old), also during a long walk
        while True:
            try:
                with open("/tmp/scanner-alive", "w", encoding="utf-8") as handle:
                    handle.write(str(time.time()))
            except OSError:
                pass
            time.sleep(30)

    threading.Thread(target=alive, name="alive", daemon=True).start()
    # Several walks at a time (different servers, or the same one up to its limit)
    for index in range(max(1, config.THREADS) - 1):
        threading.Thread(target=work, name=f"scan-{index + 2}", daemon=True).start()
    work()


def work() -> None:
    while True:
        try:
            with Session() as db:
                run = claim(db)
        except Exception:
            logger.warning("Queue not reachable", exc_info=True)
            run = None
        if not run:
            time.sleep(config.POLL_SECONDS)
            continue
        try:
            scan(run)
        except Exception as exc:
            logger.warning("Scan %s failed", run["id"], exc_info=True)
            message = f"{getattr(exc, 'code', type(exc).__name__)}: {getattr(exc, 'message', str(exc))}"[:600]
            _finish(int(run["id"]), "failed", error=message)
            try:
                core.report(int(run["storage_root_id"]), status="failed", error=message)
            except Exception:
                logger.warning("Failure not sent to the core", exc_info=True)
