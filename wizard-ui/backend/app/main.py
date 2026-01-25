from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 🔧 Infrastructure (DB helpers only, no router)
from . import db  # noqa: F401

# 🌐 Routes Wizard V1
from .routes import (
    db as db_routes,
    import_wizard as import_routes,
    runtime as runtime_routes,
)

# ============================================================
# ⚙️ WIZARD MODE
# ============================================================
WIZARD_MODE = os.getenv("WIZARD_MODE", "dev").lower()


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
    openapi_url=None,   # wizard interne
    docs_url=None,      # pas de swagger exposé
    redoc_url=None,
)

# ============================================================
# 🌐 CORS (wizard standalone)
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # wizard local
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
# 📁 STATIC UI
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

print(f"[WIZARD] Static directory: {STATIC_DIR}")

if not os.path.isdir(STATIC_DIR):
    print(f"[WIZARD][ERROR] Static directory does not exist: {STATIC_DIR}")
else:
    # Le wizard UI est servi à la racine
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

# ============================================================
# 🟢 STARTUP LOG
# ============================================================
@app.on_event("startup")
async def _startup():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  🚀 BornToShare Wizard v1.0")
    print(f"  🔧 Mode           : {WIZARD_MODE}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
