from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.routers._helpers import ui_list
from app.services.health_events import list_health_events, summarize_health_history

router = APIRouter(prefix="/health", tags=["health-events"])


@router.get("/events")
def get_health_events(
    entity_type: str,
    entity_id: int = Query(..., gt=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = list_health_events(
        db,
        entity_type=entity_type,
        entity_id=int(entity_id),
        limit=int(limit),
    )
    return ui_list(
        rows,
        meta={
            "entity_type": entity_type,
            "entity_id": int(entity_id),
            "limit": int(limit),
            "count": int(len(rows)),
        },
    )


@router.get("/summary")
def get_health_summary(
    entity_type: str,
    entity_id: int = Query(..., gt=0),
    days: int = Query(7, ge=1, le=31),
    db: Session = Depends(get_db),
):
    rows = summarize_health_history(
        db,
        entity_type=entity_type,
        entity_id=int(entity_id),
        days=int(days),
    )
    return ui_list(
        rows,
        meta={
            "entity_type": entity_type,
            "entity_id": int(entity_id),
            "days": int(days),
            "count": int(len(rows)),
        },
    )
