"""Regular infrastructure tasks (Advanced Settings › Infrastructure › Schedules).

Every 30 s, the tasks whose next run is due are started: health check and data sync. Both hand the
work to the workers through the job queue. A MariaDB lock keeps a single scheduler active when
several core-service instances run.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, engine

logger = logging.getLogger("core.infra_scheduler")

TICK_SECONDS = 30
LOCK_NAME = "b2s_infra_scheduler"


async def run_task(db: Session, task: str, *, trigger: str) -> dict[str, Any]:
    """Run one task now and record its outcome on the schedule."""
    from app.services.data_sync_service import run_data_sync
    from app.services.infrastructure_service import run_health_check

    db.execute(
        text(
            """
            UPDATE infra_schedules
            SET last_status = 'running', last_run_at = UTC_TIMESTAMP(),
                next_run_at = UTC_TIMESTAMP() + INTERVAL interval_minutes MINUTE
            WHERE task = :task
            """
        ),
        {"task": task},
    )
    db.commit()
    try:
        if task == "health_check":
            summary = await run_health_check(db, trigger=trigger)
            status = "partial" if summary.get("queued_error") or summary.get("core_down") else "success"
            message = (
                f"{summary['core_checks']} checked by core-service, {summary['worker_targets']} sent to a worker"
                + (f" · queue error: {summary['queued_error']}" if summary.get("queued_error") else "")
            )
        elif task == "data_sync":
            summary = await run_data_sync(db, trigger=trigger)
            status = summary.get("status", "success")
            message = summary.get("message", "")
        else:
            raise ValueError(f"Unknown task {task}")
    except Exception as exc:
        db.rollback()
        logger.exception("INFRA_TASK_FAILED", extra={"task": task})
        summary, status, message = {"error": str(exc)[:500]}, "failed", str(exc)[:500]
    db.execute(
        text(
            """
            UPDATE infra_schedules
            SET last_status = :status, last_message = :message, last_summary_json = :summary
            WHERE task = :task
            """
        ),
        {"task": task, "status": status, "message": str(message)[:512], "summary": json.dumps(summary, default=str)},
    )
    db.commit()
    return {"task": task, "status": status, "message": message, "summary": summary}


async def _tick() -> None:
    # The lock belongs to a connection: a dedicated one, the session commits on its own
    with engine.connect() as lock_conn:
        if not lock_conn.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": LOCK_NAME}).scalar():
            return
        try:
            await _run_due_tasks()
        finally:
            lock_conn.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": LOCK_NAME})


async def _run_due_tasks() -> None:
    db = SessionLocal()
    try:
        due = [
            row[0]
            for row in db.execute(
                text(
                    """
                    SELECT task FROM infra_schedules
                    WHERE is_enabled = 1 AND (next_run_at IS NULL OR next_run_at <= UTC_TIMESTAMP())
                    ORDER BY task
                    """
                )
            )
        ]
        for task in due:
            await run_task(db, task, trigger="schedule")
        # Log retention (Advanced Settings › Logging): once a day when enabled
        from app.services.log_retention import auto_purge_if_due

        try:
            auto_purge_if_due(db)
        except Exception:
            db.rollback()
            logger.warning("LOG_RETENTION_PURGE_FAILED", exc_info=True)
    finally:
        db.close()


async def _loop() -> None:
    await asyncio.sleep(10)  # let the service finish starting
    while True:
        try:
            await _tick()
        except Exception:
            # The scheduler must never stop the service (e.g. infrastructure tables not migrated yet)
            logger.warning("INFRA_SCHEDULER_TICK_FAILED", exc_info=True)
        await asyncio.sleep(TICK_SECONDS)


def start_infra_scheduler() -> None:
    asyncio.create_task(_loop())
