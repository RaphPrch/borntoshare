"""Advanced Settings › Infrastructure (platform administrators only)."""
from __future__ import annotations

import json
import re
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api._helpers import ui_data, ui_list
from app.core.db import get_db
from app.services import infrastructure_service as infra
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request, require_admin

router = APIRouter(prefix="/infrastructure", tags=["infrastructure"])

_HOST_RE = re.compile(r"^[A-Za-z0-9.\-:\[\]]{1,255}$")


def _admin(request: Request):
    actor = actor_from_request(request)
    require_admin(actor)
    return actor


def _audit(actor, action: str, *, target_type: str, target_id: Any = None, target_display: str | None = None, context: dict | None = None) -> None:
    log_activity(
        None,
        actor_type="user" if actor.identity_id is not None else "system",
        actor_id=actor.identity_id,
        actor_display=actor.display_name,
        action=action,
        outcome="success",
        target_type=target_type,
        target_id=target_id,
        target_display=target_display,
        context_json=context or {},
    )


# ============================================================
# Overview
# ============================================================


@router.get("/overview")
def get_overview(request: Request, db: Session = Depends(get_db)):
    _admin(request)
    data = infra.overview(db)
    data["workers"] = infra.list_workers(db)
    data["schedules"] = _schedules(db)
    data["database"] = infra.database_info()
    return ui_data(data)


# ============================================================
# Database
# ============================================================


class DatabasePayload(BaseModel):
    mode: Literal["fields", "dsn"] = "fields"
    host: Optional[str] = Field(default=None, max_length=255)
    port: Optional[int] = Field(default=3306, ge=1, le=65535)
    name: Optional[str] = Field(default=None, max_length=64)
    user: Optional[str] = Field(default=None, max_length=128)
    password: Optional[str] = Field(default=None, max_length=512)
    logging_name: Optional[str] = Field(default=None, max_length=64)
    dsn: Optional[str] = Field(default=None, max_length=1024)
    logging_dsn: Optional[str] = Field(default=None, max_length=1024)


@router.get("/database")
def get_database(request: Request):
    _admin(request)
    return ui_data(infra.database_info())


@router.post("/database/test")
def test_database(payload: DatabasePayload, request: Request):
    _admin(request)
    return ui_data(infra.test_database(payload.model_dump()))


@router.put("/database")
def save_database(payload: DatabasePayload, request: Request):
    actor = _admin(request)
    try:
        data = infra.save_database(payload.model_dump(), actor.display_name)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error_code": "RUNTIME_DIR_READ_ONLY", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"error_code": "DATABASE_TEST_FAILED", "message": str(exc)}) from exc
    configured = data.get("configured") or {}
    _audit(actor, "infrastructure.database_configured", target_type="database", target_display=f"{configured.get('host')}:{configured.get('port')}/{configured.get('name')}", context={"mode": payload.mode, "pending_restart": data.get("pending_restart")})
    return ui_data(data)


@router.delete("/database")
def reset_database(request: Request):
    actor = _admin(request)
    data = infra.reset_database()
    _audit(actor, "infrastructure.database_reset", target_type="database", context={"back_to": ".env"})
    return ui_data(data)


# ============================================================
# Workers
# ============================================================


class WorkerPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=8443, ge=1, le=65535)
    use_tls: bool = True
    verify_tls: bool = True
    username: str = Field(min_length=1, max_length=120)
    password_ref: Optional[str] = Field(default=None, max_length=512)
    is_enabled: bool = True

    @field_validator("host")
    @classmethod
    def _host(cls, value: str) -> str:
        value = value.strip()
        if not _HOST_RE.match(value):
            raise ValueError("Host name or IP address expected")
        return value


class WorkerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    host: Optional[str] = Field(default=None, min_length=1, max_length=255)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    use_tls: Optional[bool] = None
    verify_tls: Optional[bool] = None
    username: Optional[str] = Field(default=None, min_length=1, max_length=120)
    password_ref: Optional[str] = Field(default=None, max_length=512)
    is_enabled: Optional[bool] = None


@router.get("/workers")
def list_workers(request: Request, db: Session = Depends(get_db)):
    _admin(request)
    return ui_list(infra.list_workers(db))


class WorkerTestPayload(WorkerPayload):
    # Editing without a new password: the stored one of this worker is used
    worker_id: Optional[int] = None


@router.post("/workers/test")
async def test_worker(payload: WorkerTestPayload, request: Request, db: Session = Depends(get_db)):
    _admin(request)
    data = payload.model_dump()
    if not data.get("password_ref") and payload.worker_id:
        data["password_ref"] = (infra.get_worker_row(db, payload.worker_id) or {}).get("password_ref")
    if not data.get("password_ref"):
        raise HTTPException(status_code=422, detail={"error_code": "WORKER_PASSWORD_REQUIRED", "message": "The password of the agent is required"})
    return ui_data(await infra.check_agent(data))


@router.post("/workers", status_code=status.HTTP_201_CREATED)
async def create_worker(payload: WorkerPayload, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request)
    if not payload.password_ref:
        raise HTTPException(status_code=422, detail={"error_code": "WORKER_PASSWORD_REQUIRED", "message": "The password of the agent is required"})
    # A worker is added only once its agent answered with these credentials
    check = await infra.check_agent(payload.model_dump())
    if check["status"] not in {"healthy", "degraded"}:
        raise HTTPException(status_code=422, detail={"error_code": "WORKER_UNREACHABLE", "message": check.get("message") or "Agent unreachable"})
    try:
        result = db.execute(
            text(
                """
                INSERT INTO infra_workers (name, host, port, use_tls, verify_tls, username, password_ref, is_enabled)
                VALUES (:name, :host, :port, :use_tls, :verify_tls, :username, :password_ref, :is_enabled)
                """
            ),
            payload.model_dump(),
        )
        worker_id = int(result.lastrowid)
        infra.record_worker_check(db, worker_id, check)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"error_code": "WORKER_EXISTS", "message": "A worker with this name or this host and port already exists"}) from exc
    _audit(actor, "infrastructure.worker_added", target_type="worker", target_id=worker_id, target_display=payload.name, context={"host": payload.host, "port": payload.port, "tls": payload.use_tls})
    return ui_data(infra._worker_public(infra.get_worker_row(db, worker_id) or {}))


@router.patch("/workers/{worker_id}")
async def update_worker(worker_id: int, payload: WorkerUpdate, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request)
    row = infra.get_worker_row(db, worker_id)
    if not row:
        raise HTTPException(status_code=404, detail="Worker not found")
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        return ui_data(infra._worker_public(row))
    merged = {**row, **updates}
    connection_changed = any(k in updates for k in ("host", "port", "use_tls", "verify_tls", "username", "password_ref"))
    check = None
    if connection_changed and merged.get("is_enabled"):
        check = await infra.check_agent(merged)
        if check["status"] not in {"healthy", "degraded"}:
            raise HTTPException(status_code=422, detail={"error_code": "WORKER_UNREACHABLE", "message": check.get("message") or "Agent unreachable"})
    assignments = ", ".join(f"{k} = :{k}" for k in updates)
    try:
        db.execute(text(f"UPDATE infra_workers SET {assignments} WHERE id = :id"), {**updates, "id": int(worker_id)})
        if check:
            infra.record_worker_check(db, worker_id, check)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"error_code": "WORKER_EXISTS", "message": "A worker with this name or this host and port already exists"}) from exc
    _audit(actor, "infrastructure.worker_updated", target_type="worker", target_id=worker_id, target_display=merged.get("name"), context={"fields": sorted(k for k in updates if k != "password_ref") + (["password"] if "password_ref" in updates else [])})
    return ui_data(infra._worker_public(infra.get_worker_row(db, worker_id) or {}))


@router.delete("/workers/{worker_id}")
def delete_worker(worker_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request)
    row = infra.get_worker_row(db, worker_id)
    if not row:
        raise HTTPException(status_code=404, detail="Worker not found")
    db.execute(text("DELETE FROM infra_workers WHERE id = :id"), {"id": int(worker_id)})
    db.execute(text("DELETE FROM infra_component_status WHERE component = :c"), {"c": f"worker:{int(worker_id)}"})
    db.commit()
    _audit(actor, "infrastructure.worker_removed", target_type="worker", target_id=worker_id, target_display=row.get("name"))
    return ui_data({"ok": True})


@router.post("/workers/{worker_id}/check")
async def check_worker(worker_id: int, request: Request, db: Session = Depends(get_db)):
    _admin(request)
    row = infra.get_worker_row(db, worker_id)
    if not row:
        raise HTTPException(status_code=404, detail="Worker not found")
    check = await infra.check_agent(row)
    infra.record_worker_check(db, worker_id, check)
    infra.record_components(db, [{
        "component": f"worker:{worker_id}", "label": f"Worker · {row['name']}", "category": "worker",
        "status": check["status"], "latency_ms": check.get("latency_ms"), "message": check.get("message"),
    }], checked_by="core-service")
    db.commit()
    return ui_data(infra._worker_public(infra.get_worker_row(db, worker_id) or {}))


# ============================================================
# Schedules
# ============================================================


class SchedulePayload(BaseModel):
    is_enabled: Optional[bool] = None
    interval_minutes: Optional[int] = Field(default=None, ge=1, le=10080)
    options: Optional[dict[str, bool]] = None


def _schedules(db: Session) -> list[dict[str, Any]]:
    out = []
    for row in db.execute(text("SELECT * FROM infra_schedules ORDER BY task")).mappings():
        item = dict(row)
        for key in ("options_json", "last_summary_json"):
            value = item.pop(key)
            item[key.replace("_json", "")] = json.loads(value) if isinstance(value, (str, bytes)) and value else (value or {})
        item["is_enabled"] = bool(item["is_enabled"])
        for key in ("last_run_at", "next_run_at", "updated_at"):
            item[key] = infra._iso(item[key])
        out.append(item)
    return out


@router.get("/schedules")
def list_schedules(request: Request, db: Session = Depends(get_db)):
    _admin(request)
    return ui_list(_schedules(db))


@router.put("/schedules/{task}")
def update_schedule(task: Literal["health_check", "data_sync"], payload: SchedulePayload, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request)
    updates: dict[str, Any] = {}
    if payload.is_enabled is not None:
        updates["is_enabled"] = payload.is_enabled
    if payload.interval_minutes is not None:
        updates["interval_minutes"] = payload.interval_minutes
    if payload.options is not None and task == "data_sync":
        updates["options_json"] = json.dumps({k: bool(payload.options.get(k, True)) for k in ("snapshots", "shares", "acl_drift")})
    if updates:
        assignments = ", ".join(f"{k} = :{k}" for k in updates)
        # A new interval applies from now
        reschedule = ", next_run_at = UTC_TIMESTAMP() + INTERVAL :interval_minutes MINUTE" if "interval_minutes" in updates else ""
        db.execute(text(f"UPDATE infra_schedules SET {assignments}{reschedule} WHERE task = :task"), {**updates, "task": task})
        db.commit()
        _audit(actor, "infrastructure.schedule_updated", target_type="schedule", target_display=task, context={k: v for k, v in updates.items()})
    return ui_data(next(s for s in _schedules(db) if s["task"] == task))


@router.post("/schedules/{task}/run")
async def run_schedule(task: Literal["health_check", "data_sync"], request: Request, db: Session = Depends(get_db)):
    from app.jobs.infra_scheduler import run_task

    actor = _admin(request)
    running = db.execute(text("SELECT last_status FROM infra_schedules WHERE task = :task"), {"task": task}).scalar()
    if running == "running":
        raise HTTPException(status_code=409, detail={"error_code": "TASK_ALREADY_RUNNING", "message": "This task is already running"})
    result = await run_task(db, task, trigger="manual")
    _audit(actor, f"infrastructure.{task}_run", target_type="schedule", target_display=task, context={"status": result["status"]})
    return ui_data(result)


# ============================================================
# Monitored services
# ============================================================


class ServicePayload(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    category: Literal["web", "service", "data", "queue", "security", "storage", "custom"] = "custom"
    check_kind: Literal["http", "tcp"] = "http"
    target: str = Field(min_length=3, max_length=512)
    is_enabled: bool = True

    @field_validator("target")
    @classmethod
    def _target(cls, value: str, info) -> str:
        value = value.strip()
        kind = (info.data or {}).get("check_kind", "http")
        if kind == "http" and not re.match(r"^https?://", value):
            raise ValueError("An http(s):// URL is expected")
        if kind == "tcp" and not re.match(r"^[^\s/]+:\d{1,5}$", value):
            raise ValueError("host:port is expected")
        return value


def _services(db: Session) -> list[dict[str, Any]]:
    rows = [dict(r) for r in db.execute(text("SELECT * FROM infra_services ORDER BY is_builtin DESC, label")).mappings()]
    for row in rows:
        row["is_builtin"] = bool(row["is_builtin"])
        row["is_enabled"] = bool(row["is_enabled"])
        row.pop("created_at", None)
        row["updated_at"] = infra._iso(row.get("updated_at"))
    return rows


@router.get("/services")
def list_services(request: Request, db: Session = Depends(get_db)):
    _admin(request)
    return ui_list(_services(db))


@router.post("/services", status_code=status.HTTP_201_CREATED)
def create_service(payload: ServicePayload, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request)
    key = re.sub(r"[^a-z0-9]+", "_", payload.label.lower()).strip("_")[:48] or "service"
    try:
        db.execute(
            text(
                """
                INSERT INTO infra_services (component_key, label, category, check_kind, target, is_enabled)
                VALUES (:key, :label, :category, :check_kind, :target, :is_enabled)
                """
            ),
            {**payload.model_dump(), "key": f"custom_{key}"},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"error_code": "SERVICE_EXISTS", "message": "A monitored component with this name already exists"}) from exc
    _audit(actor, "infrastructure.service_added", target_type="infra_service", target_display=payload.label, context={"target": payload.target})
    return ui_list(_services(db))


@router.put("/services/{service_id}")
def update_service(service_id: int, payload: ServicePayload, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request)
    row = db.execute(text("SELECT * FROM infra_services WHERE id = :id"), {"id": service_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Monitored component not found")
    db.execute(
        text("UPDATE infra_services SET label = :label, category = :category, check_kind = :check_kind, target = :target, is_enabled = :is_enabled WHERE id = :id"),
        {**payload.model_dump(), "id": service_id},
    )
    if not payload.is_enabled:
        db.execute(text("DELETE FROM infra_component_status WHERE component = :c"), {"c": f"service:{row['component_key']}"})
    db.commit()
    _audit(actor, "infrastructure.service_updated", target_type="infra_service", target_id=service_id, target_display=payload.label, context={"target": payload.target, "enabled": payload.is_enabled})
    return ui_list(_services(db))


@router.delete("/services/{service_id}")
def delete_service(service_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request)
    row = db.execute(text("SELECT * FROM infra_services WHERE id = :id"), {"id": service_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Monitored component not found")
    if row["is_builtin"]:
        raise HTTPException(status_code=409, detail={"error_code": "SERVICE_BUILTIN", "message": "A platform component can be disabled, not deleted"})
    db.execute(text("DELETE FROM infra_services WHERE id = :id"), {"id": service_id})
    db.execute(text("DELETE FROM infra_component_status WHERE component = :c"), {"c": f"service:{row['component_key']}"})
    db.commit()
    _audit(actor, "infrastructure.service_removed", target_type="infra_service", target_id=service_id, target_display=row["label"])
    return ui_list(_services(db))


# ============================================================
# SSO providers (Keycloak)
# ============================================================


class RoleMappingItem(BaseModel):
    value: str = Field(min_length=1, max_length=190)
    role: str = Field(min_length=1, max_length=64)


class SsoProviderPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=8, max_length=512)
    realm: str = Field(min_length=1, max_length=120)
    client_id: str = Field(min_length=1, max_length=190)
    client_secret_ref: Optional[str] = Field(default=None, max_length=512)
    public_client: bool = False
    scopes: str = Field(default="openid profile email", max_length=255)
    username_claim: str = Field(default="preferred_username", max_length=64)
    roles_claim: str = Field(default="realm_access.roles", max_length=190)
    role_mapping: list[RoleMappingItem] = Field(default_factory=list, max_length=100)
    default_role: Optional[str] = Field(default=None, max_length=64)
    link_existing_identities: bool = True
    button_label: Optional[str] = Field(default=None, max_length=120)
    verify_tls: bool = True
    is_enabled: bool = True

    @field_validator("base_url")
    @classmethod
    def _base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not re.match(r"^https?://[^\s/]+", value):
            raise ValueError("An http(s):// URL is expected")
        if "/realms/" in value:
            raise ValueError("Give the server URL without /realms/<realm> (the realm has its own field)")
        return value

    @field_validator("scopes")
    @classmethod
    def _scopes(cls, value: str) -> str:
        scopes = value.split()
        if "openid" not in scopes:
            scopes.insert(0, "openid")
        return " ".join(scopes)


def _check_roles(db: Session, payload: SsoProviderPayload) -> None:
    known = {r[0] for r in db.execute(text("SELECT code FROM roles"))}
    used = {m.role for m in payload.role_mapping} | ({payload.default_role} if payload.default_role else set())
    unknown = sorted(used - known)
    if unknown:
        raise HTTPException(status_code=422, detail={"error_code": "UNKNOWN_ROLE", "message": f"Unknown role(s): {', '.join(unknown)}"})


@router.get("/sso")
def list_sso_providers(request: Request, db: Session = Depends(get_db)):
    from app.services import sso_service

    _admin(request)
    roles = [dict(r) for r in db.execute(text("SELECT code, label FROM roles ORDER BY id")).mappings()]
    return ui_data({"providers": sso_service.list_providers(db), "roles": roles})


@router.post("/sso", status_code=status.HTTP_201_CREATED)
def create_sso_provider(payload: SsoProviderPayload, request: Request, db: Session = Depends(get_db)):
    from app.services import sso_service

    actor = _admin(request)
    _check_roles(db, payload)
    if not payload.public_client and not payload.client_secret_ref:
        raise HTTPException(status_code=422, detail={"error_code": "CLIENT_SECRET_REQUIRED", "message": "The client secret is required (or mark the client as public)"})
    try:
        provider = sso_service.save_provider(db, payload.model_dump())
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"error_code": "SSO_PROVIDER_EXISTS", "message": "A provider with this name, or this realm and client, already exists"}) from exc
    _audit(actor, "infrastructure.sso_provider_added", target_type="sso_provider", target_id=provider["id"], target_display=payload.name, context={"realm": payload.realm, "client_id": payload.client_id})
    return ui_data(provider)


@router.put("/sso/{provider_id}")
def update_sso_provider(provider_id: int, payload: SsoProviderPayload, request: Request, db: Session = Depends(get_db)):
    from app.services import sso_service

    actor = _admin(request)
    if not sso_service.get_provider_row(db, provider_id):
        raise HTTPException(status_code=404, detail="SSO provider not found")
    _check_roles(db, payload)
    try:
        provider = sso_service.save_provider(db, payload.model_dump(), provider_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"error_code": "SSO_PROVIDER_EXISTS", "message": "A provider with this name, or this realm and client, already exists"}) from exc
    _audit(actor, "infrastructure.sso_provider_updated", target_type="sso_provider", target_id=provider_id, target_display=payload.name, context={"enabled": payload.is_enabled, "secret_changed": bool(payload.client_secret_ref)})
    return ui_data(provider)


@router.delete("/sso/{provider_id}")
def delete_sso_provider(provider_id: int, request: Request, db: Session = Depends(get_db)):
    from app.services import sso_service

    actor = _admin(request)
    row = sso_service.get_provider_row(db, provider_id)
    if not row:
        raise HTTPException(status_code=404, detail="SSO provider not found")
    sso_service.delete_provider(db, provider_id)
    db.execute(text("DELETE FROM infra_component_status WHERE component = :c"), {"c": f"sso:{int(provider_id)}"})
    db.commit()
    _audit(actor, "infrastructure.sso_provider_removed", target_type="sso_provider", target_id=provider_id, target_display=row.get("name"))
    return ui_data({"ok": True})


class SsoStatusPayload(BaseModel):
    status: Literal["healthy", "down"]
    message: str = Field(default="", max_length=512)


@router.post("/sso/{provider_id}/status")
def record_sso_status(provider_id: int, payload: SsoStatusPayload, request: Request, db: Session = Depends(get_db)):
    """Result of « Test » (run by auth-service, which holds the client secret)."""
    _admin(request)
    db.execute(
        text("UPDATE sso_providers SET status = :status, last_message = :message, last_check_at = UTC_TIMESTAMP() WHERE id = :id"),
        {"status": payload.status, "message": payload.message, "id": int(provider_id)},
    )
    db.commit()
    return ui_data({"ok": True})
