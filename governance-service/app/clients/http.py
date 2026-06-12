from __future__ import annotations
import httpx
from app.core.settings import get_settings

settings = get_settings()

def client(base_url: str, timeout: float | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=timeout or 10.0)
