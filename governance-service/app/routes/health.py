from fastapi import APIRouter

from app.schemas.api_envelopes import data_envelope

router = APIRouter()

@router.get("/api/health")
def api_health():
    return data_envelope({"ok": True})
