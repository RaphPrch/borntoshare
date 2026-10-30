from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.api._helpers import ui_list
from app.services.health_events import summarize_health_history
from app.services.authorization import admin_or_internal

router = APIRouter(prefix="/health", tags=["health-events"])


@router.get("/summary", dependencies=[Depends(admin_or_internal)])
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
