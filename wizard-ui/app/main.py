from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 🔧 Infrastructure (DB helpers only, no router side-effects)
from . import db  # noqa: F401  (import volontaire pour init DB)

# 🌐 Routes Wizard V1
from .routes import (
    db as db_routes,
    import_wizard as import_routes,
    runtime as runtime_routes,
)

# ============================================================
# ⚙️ WIZARD MODE
# ============================================================
WIZARD_MODE = os.getenv("WIZARD_MODE", "dev").strip().lower()


def is_dev() -> bool:
    return WIZARD_MODE == "dev"


def is_prod() -> bool:
    return WIZARD_MODE == "prod"


# ============================================================
# 🚀 FASTAPI INIT
# ============================================================
app = FastAPI(
    title="BornToShare Wizard",
    version="1.0",
    description="Initial setup wizard for BornToShare platform",
    openapi_url=None,   # wizard interne
    docs_url=None,
    redoc_url=None,
)

# ============================================================
# 🌐 CORS (wizard standalone)
# ============================================================
# Wizard = outil local / bootstrap → permissif assumé
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 🔧 MODE ENDPOINT (UI / sanity check)
# ============================================================
@app.get("/api/mode")
async def get_mode():
    return {
        "mode": WIZARD_MODE,
        "is_dev": is_dev(),
        "is_prod": is_prod(),
    }

# ============================================================
# 📌 API ROUTES (V1)
# ============================================================
# IMPORTANT :
# - Chaque router définit SON prefix interne
# - /api est ajouté ICI et UNIQUEMENT ICI
app.include_router(db_routes.router, prefix="/api")
app.include_router(import_routes.router, prefix="/api")
app.include_router(runtime_routes.router, prefix="/api")

# ============================================================
# 📁 STATIC UI (Wizard Frontend)
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

print(f"[WIZARD] Static directory: {STATIC_DIR}")

if os.path.isdir(STATIC_DIR):
    # Le wizard UI est servi à la racine (/)
    app.mount(
        "/",
        StaticFiles(directory=STATIC_DIR, html=True),
        name="wizard-ui",
    )
else:
    print(f"[WIZARD][WARN] Static directory not found: {STATIC_DIR}")

# ============================================================
# 🟢 STARTUP LOG
# ============================================================
@app.on_event("startup")
async def _startup() -> None:
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  🚀 BornToShare Wizard")
    print(f"  🔧 Mode           : {WIZARD_MODE}")
    print(f"  📁 Static UI      : {bool(os.path.isdir(STATIC_DIR))}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
