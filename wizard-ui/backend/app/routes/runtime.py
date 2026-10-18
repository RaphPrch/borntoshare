from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/runtime", tags=["runtime"])

log = logging.getLogger("wizard")


# ============================================================
# 📚 LOGGING (UI → backend)
# ============================================================

class LogRequest(BaseModel):
    level: str = Field(..., description="Log level (info, warning, error, etc.)")
    message: str = Field(..., description="Message de log à enregistrer")


@router.post("/log")
async def log_event(log_data: LogRequest):
    """
    Route pour recevoir des logs et les enregistrer dans les fichiers ou les afficher.
    """
    level = log_data.level.lower()
    message = log_data.message

    if level == "info":
        log.info(message)
    elif level == "warning":
        log.warning(message)
    elif level == "error":
        log.error(message)
    else:
        raise HTTPException(status_code=400, detail="Niveau de log invalide. Utilisez 'info', 'warning', ou 'error'.")

    return {"message": "Log enregistré avec succès"}
