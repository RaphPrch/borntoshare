"""History of the measures of a governed folder (pack 155): its growth, and when its quota will be full.

Each successful measure by the worker adds a point (at most one per hour per folder: a second measure in the
same hour replaces the first). The trend is a least-squares line over the last 90 days; it is only given once the
points cover a week, so that a burst of measures on one day never predicts nonsense.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

TREND_DAYS = 90
MIN_SPAN_DAYS = 7


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _int(value: Any) -> int | None:
    try:
        return None if value is None or value == "" else int(value)
    except (TypeError, ValueError):
        return None


def record(storage_root_id: int, *, measured_at: datetime | None, bytes_: int, stats: dict | None) -> None:
    """One more point. In its own short transaction (retried when the database picks it as a deadlock victim):
    many measures land at the same time, and a failure here must never cost the measure itself."""
    import time

    from sqlalchemy.exc import OperationalError

    from app.core.db import SessionLocal

    stats = stats if isinstance(stats, dict) else {}
    when = (measured_at or _now()).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    cold = stats.get("cold") if isinstance(stats.get("cold"), dict) else {}
    values = {
        "id": int(storage_root_id), "at": when, "bytes": int(bytes_),
        "files": _int(stats.get("files")), "folders": _int(stats.get("folders")),
        "cold1": _int((cold.get("1y") or {}).get("bytes")), "cold3": _int((cold.get("3y") or {}).get("bytes")),
        "junk": _int((stats.get("junk") or {}).get("bytes")) if isinstance(stats.get("junk"), dict) else None,
    }
    statement = text(
        """
        INSERT INTO storage_root_content_history (storage_root_id, measured_at, bytes, files, folders, cold_1y_bytes, cold_3y_bytes, junk_bytes)
        VALUES (:id, :at, :bytes, :files, :folders, :cold1, :cold3, :junk)
        ON DUPLICATE KEY UPDATE bytes = VALUES(bytes), files = VALUES(files), folders = VALUES(folders),
          cold_1y_bytes = VALUES(cold_1y_bytes), cold_3y_bytes = VALUES(cold_3y_bytes), junk_bytes = VALUES(junk_bytes)
        """
    )
    for attempt in range(3):
        session = SessionLocal()
        try:
            session.execute(statement, values)
            session.commit()
            return
        except OperationalError:
            session.rollback()
            if attempt == 2:
                raise
            time.sleep(0.2 * (attempt + 1))
        finally:
            session.close()


def points(db: Session, storage_root_id: int, days: int = 180) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT measured_at, bytes, files, cold_1y_bytes, junk_bytes FROM storage_root_content_history
            WHERE storage_root_id = :id AND measured_at >= :since ORDER BY measured_at
            """
        ),
        {"id": int(storage_root_id), "since": _now() - timedelta(days=days)},
    ).mappings().all()
    return [{"at": row["measured_at"].isoformat() + "Z", "bytes": int(row["bytes"]), "files": _int(row["files"]),
             "cold_1y_bytes": _int(row["cold_1y_bytes"]), "junk_bytes": _int(row["junk_bytes"])} for row in rows]


def slope_per_day(series: list[tuple[datetime, int]]) -> float | None:
    """Bytes per day (least squares), or None while the points cover less than a week."""
    if len(series) < 2:
        return None
    start = series[0][0]
    xs = [(at - start).total_seconds() / 86400 for at, _ in series]
    if xs[-1] - xs[0] < MIN_SPAN_DAYS:
        return None
    ys = [float(value) for _, value in series]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    var = sum((x - mean_x) ** 2 for x in xs)
    if var == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / var


def _series(db: Session, storage_root_ids: list[int]) -> dict[int, list[tuple[datetime, int]]]:
    ids = sorted({int(value) for value in storage_root_ids if int(value) > 0})
    if not ids:
        return {}
    try:
        rows = db.execute(
            text(
                "SELECT storage_root_id, measured_at, bytes FROM storage_root_content_history "
                "WHERE storage_root_id IN :ids AND measured_at >= :since ORDER BY measured_at"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": ids, "since": _now() - timedelta(days=TREND_DAYS)},
        ).all()
    except Exception:
        db.rollback()
        return {}
    out: dict[int, list[tuple[datetime, int]]] = {}
    for root_id, at, value in rows:
        out.setdefault(int(root_id), []).append((at, int(value)))
    return out


def forecast(current: int | None, limit: int | None, slope: float | None) -> dict[str, Any]:
    """When the quota will be full at this pace (None: no quota, no trend, or not growing)."""
    if current is None or not limit or slope is None or slope <= 0:
        return {"days_until_full": None, "full_at": None}
    if current >= limit:
        return {"days_until_full": 0, "full_at": _now().isoformat() + "Z"}
    days = (limit - current) / slope
    if days > 3650:
        return {"days_until_full": None, "full_at": None}
    return {"days_until_full": int(days), "full_at": (_now() + timedelta(days=days)).isoformat() + "Z"}


def trends(db: Session, storage_root_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Per folder: growth over 30 days and bytes per day (list, reports, 5S)."""
    out: dict[int, dict[str, Any]] = {}
    since = _now() - timedelta(days=30)
    for root_id, series in _series(db, storage_root_ids).items():
        recent = [value for at, value in series if at >= since]
        before = [value for at, value in series if at < since]
        base = before[-1] if before else (recent[0] if recent else None)
        out[root_id] = {
            "bytes_per_day": slope_per_day(series),
            "growth_30d_bytes": (series[-1][1] - base) if base is not None and len(series) > 1 else None,
            "measures": len(series),
        }
    return out


def summary(db: Session, storage_root_id: int, quota_limit: int | None) -> dict[str, Any]:
    """The card of the folder: the points, the pace and the date the quota will be full."""
    series = points(db, storage_root_id)
    slope = slope_per_day([(datetime.fromisoformat(p["at"][:-1]), p["bytes"]) for p in series if p["at"]])
    current = series[-1]["bytes"] if series else None
    return {"points": series, "bytes_per_day": slope, **forecast(current, quota_limit, slope),
            "trend_after_days": MIN_SPAN_DAYS}
