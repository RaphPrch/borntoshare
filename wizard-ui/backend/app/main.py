"""BornToShare installation wizard: creates the databases (BornToShare, its audit, the 5S module), the SQL accounts,
the first administrator and records the license. Run once (make wizard), then stopped (make wizard-down)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import install
from .license import LicenseError, decode

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
logger = logging.getLogger("wizard")
logging.getLogger("mysql.connector").setLevel(logging.WARNING)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="BornToShare — installation", openapi_url=None, docs_url=None, redoc_url=None)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


def _env(name: str, default: str) -> str:
    return (os.getenv(name) or "").strip() or default


@app.get("/api/defaults")
def defaults() -> dict[str, Any]:
    """What .env already says (names only: the passwords of the accounts are generated): the fields start from it."""
    return {
        "server": {"host": _env("DB_HOST", ""), "port": int(_env("DB_PORT", "3306"))},
        "app": {"db_name": _env("DB_NAME", "borntoshare"), "logging_db_name": _env("LOGGING_DB_NAME", "borntoshare_logging"),
                "user": _env("DB_USER", "b2s_core"), "migrate_user": _env("DB_MIGRATE_USER", "b2s_migrate")},
        "fives": {"db_name": _env("FIVES_DB_NAME", "b2s_fives"), "inventory_db_name": _env("FIVES_INVENTORY_DB_NAME", "b2s_fives_inventory"),
                  "user": _env("FIVES_DB_USER", "b2s_fives")},
    }


class Server(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=3306, ge=1, le=65535)
    user: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=512)


@app.post("/api/server/check")
def check_server(server: Server) -> dict[str, Any]:
    try:
        return install.check_server(server.model_dump())
    except Exception as exc:
        logger.warning("[SERVER] %s:%s refused: %s", server.host, server.port, exc)
        raise HTTPException(status_code=400, detail=f"Connexion impossible : {str(exc)[:300]}") from exc


class LicenseKey(BaseModel):
    key: str = Field(min_length=1, max_length=4000)


@app.post("/api/license/check")
def check_license(payload: LicenseKey) -> dict[str, Any]:
    try:
        return decode(payload.key).public()
    except LicenseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class Plan(BaseModel):
    server: dict[str, Any]
    app: dict[str, Any]
    admin: dict[str, Any]
    # The access governance (included) and the 5S (licensed): at least one
    modules: Optional[dict[str, Any]] = None
    license: Optional[str] = Field(default=None, max_length=4000)
    fives: Optional[dict[str, Any]] = None


@app.post("/api/install")
def run_install(payload: Plan) -> dict[str, Any]:
    try:
        plan = install.validate(payload.model_dump())
    except (install.InstallError, LicenseError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("[INSTALL] start: %s, %s, module 5S %s", plan["app"]["db_name"], plan["app"]["logging_db_name"], "yes" if plan["fives"] else "no")
    result = install.run(plan)
    logger.info("[INSTALL] %s", "done" if result["ok"] else "stopped")
    return result


@app.get("/api/deploy")
def deploy_status() -> dict[str, Any]:
    """The automatic deployment after the installation (scripts/after-wizard.sh on the host), and where to open BornToShare."""
    return {**install.deploy_status(), "app_url": _env("FRONTEND_PUBLIC_ORIGIN", "")}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")
