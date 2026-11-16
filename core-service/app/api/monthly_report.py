"""The monthly report (Settings › Notifications): its preview, and sending it now."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.services import monthly_report
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request, admin_only

router = APIRouter(prefix="/monthly-report", tags=["monthly-report"])


class SendNow(BaseModel):
    # One address to try it; none: the administrators
    to: str | None = Field(default=None, max_length=254)


@router.get("/preview", dependencies=[Depends(admin_only)])
def preview_monthly_report(db: Session = Depends(get_db)):
    """The last 30 days, as the report would show them."""
    until = monthly_report._now()
    since = until - timedelta(days=30)
    data = monthly_report.build(db, since, until)
    return ui_data({"label": "30 derniers jours", "sections": monthly_report.lines(data), "data": data})


@router.post("/send", dependencies=[Depends(admin_only)])
def send_monthly_report(payload: SendNow, request: Request, db: Session = Depends(get_db)):
    """The report of the last 30 days, now (to one address, or to the administrators)."""
    until = monthly_report._now()
    result = monthly_report.send(db, since=until - timedelta(days=30), until=until, label="30 derniers jours",
                                 key=f"monthly_report:now:{until:%Y%m%d%H%M%S}", recipients=[payload.to] if payload.to else None)
    actor = actor_from_request(request)
    log_activity(None, actor_type="user", actor_id=actor.identity_id, actor_display=actor.display_name, action="infrastructure.monthly_report_sent",
                 outcome="success", target_type="infrastructure", target_display="Rapport mensuel",
                 context_json={"count": len(result["recipients"]), "reason": ", ".join(result["recipients"])[:300]})
    return ui_data({"recipients": result["recipients"], "mail_enabled": result["mail_enabled"]})
