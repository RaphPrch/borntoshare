from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.core.internal_auth import require_internal_token
from app.services import domain_dns
from app.services.authorization import admin_only

router = APIRouter(tags=["network"])


@router.get("/internal/network/dns", dependencies=[Depends(require_internal_token)])
def dns_for_the_worker(db: Session = Depends(get_db)):
    """Domains and their DNS servers, as the worker uses them."""
    return ui_data([{"domain": e["domain"], "servers": e["servers"], "fallback": bool(e.get("fallback"))} for e in domain_dns.effective(db)])


@router.get("/admin/network/dns", dependencies=[Depends(admin_only)])
def dns_settings(db: Session = Depends(get_db)):
    """The domains set by an administrator, and those the directories propose."""
    return ui_data({"configured": domain_dns.configured(db), "proposed": domain_dns.proposed(db)})
