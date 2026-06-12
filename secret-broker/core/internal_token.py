from __future__ import annotations

from typing import Dict
from core.settings import settings

def build_internal_headers() -> Dict[str, str]:
    tok = (settings.internal_token or "").strip()
    return {"X-Internal-Token": tok} if tok else {}
