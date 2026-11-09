"""History of the measures of each folder (b2s_fives.content_history): the growth curve, and when the quota will be full.

The core sends each measure to the module (/internal/measures). At most one point per folder and hour (a second
measure in the same hour replaces the first, one statement, no lock race). The trend is a least-squares line over
the last 90 days, given only once the points cover a week.
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


def record(db: Session, storage_root_id: int, *, measured_at: datetime, bytes_: int, stats: dict | None) -> None:
    stats = stats if isinstance(stats, dict) else {}
    cold = stats.get("cold") if isinstance(stats.get("cold"), dict) else {}
    dups = stats.get("duplicates") if isinstance(stats.get("duplicates"), dict) else {}
    junk = stats.get("junk") if isinstance(stats.get("junk"), dict) else {}
    db.execute(
        text(
            """
            INSERT INTO content_history (storage_root_id, measured_at, bytes, files, folders, cold_1y_bytes, cold_3y_bytes, junk_bytes, duplicate_bytes)
            VALUES (:id, :at, :bytes, :files, :folders, :cold1, :cold3, :junk, :dup)
            ON DUPLICATE KEY UPDATE bytes = VALUES(bytes), files = VALUES(files), folders = VALUES(folders), cold_1y_bytes = VALUES(cold_1y_bytes),
              cold_3y_bytes = VALUES(cold_3y_bytes), junk_bytes = VALUES(junk_bytes), duplicate_bytes = VALUES(duplicate_bytes)
            """
        ),
        {"id": int(storage_root_id), "at": measured_at.replace(minute=0, second=0, microsecond=0, tzinfo=None), "bytes": int(bytes_),
         "files": _int(stats.get("files")), "folders": _int(stats.get("folders")),
         "cold1": _int((cold.get("1y") or {}).get("bytes")), "cold3": _int((cold.get("3y") or {}).get("bytes")),
         "junk": _int(junk.get("bytes")), "dup": _int(dups.get("wasted_bytes"))},
    )


def points(db: Session, storage_root_id: int, days: int = 180) -> list[dict[str, Any]]:
    rows = db.execute(
        text("SELECT measured_at, bytes, files FROM content_history WHERE storage_root_id = :id AND measured_at >= :since ORDER BY measured_at"),
        {"id": int(storage_root_id), "since": _now() - timedelta(days=days)},
    ).mappings().all()
    return [{"at": row["measured_at"].isoformat() + "Z", "bytes": int(row["bytes"]), "files": _int(row["files"])} for row in rows]


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
    """Per folder: growth over 30 days and bytes per day (5S, reports)."""
    ids = sorted({int(value) for value in storage_root_ids if int(value) > 0})
    if not ids:
        return {}
    rows = db.execute(
        text("SELECT storage_root_id, measured_at, bytes FROM content_history WHERE storage_root_id IN :ids AND measured_at >= :since ORDER BY measured_at")
        .bindparams(bindparam("ids", expanding=True)),
        {"ids": ids, "since": _now() - timedelta(days=TREND_DAYS)},
    ).all()
    series: dict[int, list[tuple[datetime, int]]] = {}
    for root_id, at, value in rows:
        series.setdefault(int(root_id), []).append((at, int(value)))
    since = _now() - timedelta(days=30)
    out: dict[int, dict[str, Any]] = {}
    for root_id, items in series.items():
        before = [value for at, value in items if at < since]
        recent = [value for at, value in items if at >= since]
        base = before[-1] if before else (recent[0] if recent else None)
        out[root_id] = {"bytes_per_day": slope_per_day(items), "measures": len(items),
                        "growth_30d_bytes": (items[-1][1] - base) if base is not None and len(items) > 1 else None}
    return out


def summary(db: Session, storage_root_id: int, quota_limit: int | None) -> dict[str, Any]:
    series = points(db, storage_root_id)
    slope = slope_per_day([(datetime.fromisoformat(p["at"][:-1]), p["bytes"]) for p in series])
    current = series[-1]["bytes"] if series else None
    return {"points": series, "bytes_per_day": slope, **forecast(current, quota_limit, slope), "trend_after_days": MIN_SPAN_DAYS}
