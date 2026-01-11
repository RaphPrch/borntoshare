from fastapi import APIRouter
from app.core.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger(__name__)

@router.get("/health")
async def health():
    logger.debug("/health called")
    return {"status":"ok","service":"auth-service"}
