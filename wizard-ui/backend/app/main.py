from __future__ import annotations

import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# 🔧 Infrastructure (DB helpers only, no router)
from . import db  # noqa: F401

# 🌐 Routes Wizard V1
from .routes import (
    db as db_routes,
    import_wizard as import_routes,
    runtime as runtime_routes,
)
from .logging_db import DBLogHandler, logging_store

# ============================================================
# 🔊 LOGGING CONFIGURATION (CRITICAL)
# ============================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

logging.getLogger("uvicorn").setLevel(LOG_LEVEL)
logging.getLogger("uvicorn.error").setLevel(LOG_LEVEL)
logging.getLogger("uvicorn.access").setLevel(LOG_LEVEL)

logger = logging.getLogger("wizard")

logger.info("Logging initialized", extra={"level": LOG_LEVEL})


def _is_missing_database_error(exc: Exception) -> bool:
    errno = getattr(exc, "errno", None)
    if errno == 1049:
        return True

    msg = str(exc).lower()
    return "unknown database" in msg

db_logging_ready = False

try:
    logging_store.ensure_schema()
    db_cfg = logging_store.get_config()
    configured_level = (db_cfg.get("level") or LOG_LEVEL).upper()
    if configured_level == "WARN":
        configured_level = "WARNING"

    root_level = getattr(logging, configured_level, getattr(logging, LOG_LEVEL, logging.INFO))
    logging.getLogger().setLevel(root_level)
    db_logging_ready = True
except Exception as exc:
    if _is_missing_database_error(exc):
        logger.warning("Logging DB not initialized yet (missing database), fallback to env LOG_LEVEL")
    else:
        logger.warning("DB logging config unavailable, fallback to env LOG_LEVEL", exc_info=exc)

if db_logging_ready:
    db_handler = DBLogHandler(logging_store)
    db_handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(db_handler)
else:
    logger.info("DB log handler disabled until logging DB is initialized")

# ============================================================
# ⚙️ WIZARD MODE
# ============================================================
# Priority:
# - WIZARD_MODE (explicit)
# - APP_ENV (compose / container)
# - default: dev
WIZARD_MODE = os.getenv("WIZARD_MODE", os.getenv("APP_ENV", "dev")).lower()


def is_dev() -> bool:
    return WIZARD_MODE == "dev"


def is_prod() -> bool:
    return WIZARD_MODE == "prod"



# ============================================================
# 🚀 FASTAPI INIT
# ============================================================
app = FastAPI(
    title="BornToShare Wizard v1.0",
    description="Initial setup wizard for BornToShare platform",
    openapi_url=None,   # Wizard interne
    docs_url=None,      # Pas de Swagger exposé
    redoc_url=None,
)

# ============================================================
# 🌐 CORS (wizard standalone)
# ============================================================
# NOTE:
# - Wizard interne
# - En PROD publique, les origins devront être restreintes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 🟢 HEALTHCHECK (PROD / SUPERVISION)
# ============================================================
@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


# ============================================================
# 🔧 MODE ENDPOINT (UI)
# ============================================================
@app.get("/api/mode")
async def get_mode():
    return {
        "mode": WIZARD_MODE,
        "dev": is_dev(),
        "prod": is_prod(),
    }


# ============================================================
# 📌 API ROUTES (V1)
# ============================================================
# IMPORTANT :
# - db.router       → prefix="/db"
# - import.router   → prefix="/import"
# - runtime.router  → prefix="/runtime"
# => /api est ajouté ICI et UNIQUEMENT ICI
app.include_router(db_routes.router, prefix="/api")
app.include_router(import_routes.router, prefix="/api")
app.include_router(runtime_routes.router, prefix="/api")

# ============================================================
# 📁 STATIC UI (PROD SAFE)
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

print(f"[WIZARD] Static directory: {STATIC_DIR}")

if not os.path.isdir(STATIC_DIR):
    raise RuntimeError(f"[WIZARD][FATAL] Static directory missing: {STATIC_DIR}")

# Assets (CSS, JS, images…)
app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)

# Root → index.html
@app.get("/", include_in_schema=False)
async def wizard_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ============================================================
# 🟢 STARTUP LOG
# ============================================================
@app.on_event("startup")
async def _startup():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  🚀 BornToShare Wizard v1.0")
    print(f"  🔧 Mode           : {WIZARD_MODE}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
