from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.session_store import RedisSessionStore, get_session_store

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    """Container healthcheck: answers 503 when the session store (Redis) cannot be reached."""
    checks: dict[str, str] = {}
    store = get_session_store()
    if isinstance(store, RedisSessionStore):
        try:
            store.ping()
            checks["sessions"] = "ok"
        except Exception as exc:
            checks["sessions"] = str(exc)[:200]
    healthy = all(value == "ok" for value in checks.values())
    body = {"status": "ok" if healthy else "down", "service": "auth-service", "checks": checks}
    return body if healthy else JSONResponse(status_code=503, content=body)
