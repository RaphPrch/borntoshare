from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db import test_connection

router = APIRouter(
    prefix="/db",
    tags=["wizard-db"],
)

class DbTestPayload(BaseModel):
    host: str
    port: int = 3306
    user: str
    password: str
    database: str | None = None


@router.post("/test")
async def test_db(payload: DbTestPayload):
    ok = test_connection({
        "host": payload.host,
        "port": payload.port,
        "user": payload.user,
        "password": payload.password,
        "database": payload.database,
    })

    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Unable to connect to database with provided credentials",
        )

    return {
        "status": "ok",
        "message": "Database connection successful",
    }
