"""Smart policies (Policies page): « if the folders match this condition, then tag / alert / tell the guardians »."""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.services import folder_query
from app.services import policies as engine
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request, require_admin

router = APIRouter(prefix="/policies", tags=["policies"])


class PolicyAlert(BaseModel):
    severity: Literal["info", "warning", "high", "critical"] = "warning"


class PolicyJobs(BaseModel):
    # check: test the folder and read its ACL again; measure: size, age, clutter, duplicates; sensitivity: scan
    kinds: list[Literal["check", "measure", "sensitivity"]] = Field(min_length=1, max_length=3)
    every_hours: Literal[24, 168, 720] = 168


class PolicyActions(BaseModel):
    add_tag: int | None = Field(default=None, gt=0)
    # The tag goes with the condition: removed when the folder no longer matches (automatic tags)
    remove_tag: bool = False
    # The tag also on the sub-folders that match (their name for chemin:, the files found in them for est:…)
    subfolders: bool = False
    alert: PolicyAlert | None = None
    notify_guardians: bool = False
    jobs: PolicyJobs | None = None


class PolicyPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool = True
    condition: str = Field(min_length=1, max_length=500)
    actions: PolicyActions = Field(default_factory=PolicyActions)


class PreviewPayload(BaseModel):
    condition: str = Field(min_length=1, max_length=500)


def _check(db: Session, payload: PolicyPayload) -> None:
    unknown = folder_query.unknown_states(payload.condition)
    if unknown:
        raise HTTPException(status_code=422, detail={"code": "POLICY_CONDITION_INVALID", "message": f"État inconnu : {', '.join(unknown)}"})
    actions = payload.actions
    if not (actions.add_tag or actions.alert or actions.notify_guardians or actions.jobs):
        raise HTTPException(status_code=422, detail={"code": "POLICY_NO_ACTION", "message": "Choisissez au moins une action"})
    if actions.add_tag and not engine.tag_exists(db, actions.add_tag):
        raise HTTPException(status_code=422, detail={"code": "POLICY_TAG_UNKNOWN", "message": "Ce tag n'existe pas"})
    if actions.subfolders:
        from app.services.folder_tags import supported

        if not actions.add_tag:
            raise HTTPException(status_code=422, detail={"code": "POLICY_SUBFOLDERS_NEED_TAG", "message": "Les sous-dossiers reçoivent un tag : choisissez-le"})
        if not supported(payload.condition):
            raise HTTPException(status_code=422, detail={"code": "POLICY_SUBFOLDERS_UNSUPPORTED",
                                                         "message": "Sur les sous-dossiers, seuls chemin:… et les états de sensibilité (est:mot-de-passe, est:sensible…) sont évalués"})


def _audit(db: Session, request: Request, action: str, policy_id: int, name: str, context: dict | None = None) -> None:
    actor = actor_from_request(request)
    log_activity(
        db, actor_type="user", actor_id=actor.identity_id, actor_display=actor.display_name,
        action=action, outcome="success", target_type="policy", target_id=str(policy_id), target_display=name,
        context_json=context or {}, correlation_id=(request.headers.get("x-request-id") or None),
    )


@router.get("")
def list_policies(request: Request, db: Session = Depends(get_db)):
    require_admin(actor_from_request(request))
    hits = engine.hit_counts(db)
    return ui_data([{**policy, "matching": hits.get(policy["id"], 0)} for policy in engine.list_policies(db)])


@router.post("/preview")
def preview(payload: PreviewPayload, request: Request, db: Session = Depends(get_db)):
    """The folders the condition matches now (the same evaluation as the runs)."""
    require_admin(actor_from_request(request))
    unknown = folder_query.unknown_states(payload.condition)
    rows = engine.matching(engine.folder_rows(db), payload.condition)
    return ui_data({
        "count": len(rows),
        "unknown_states": unknown,
        "sample": [{"id": int(row["storage_root_id"]), "name": row.get("storage_root_name"), "path": row.get("dfs_path") or row.get("root_path")} for row in rows[:8]],
    })


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_policy(payload: PolicyPayload, request: Request, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    require_admin(actor)
    _check(db, payload)
    policy_id = engine.save_policy(db, None, name=payload.name, description=payload.description, enabled=payload.enabled,
                                   condition=payload.condition, actions=payload.actions.model_dump(), by=actor.display_name)
    _audit(db, request, "policy.created", policy_id, payload.name, {"condition": payload.condition, "actions": payload.actions.model_dump()})
    # Applied at once: no need to wait for the next run of the schedule
    summary = await engine.run_all_and_dispatch(db, policy_id=policy_id, trigger="admin") if payload.enabled else None
    return ui_data({"policy": engine.get_policy(db, policy_id), "run": summary})


@router.put("/{policy_id}")
async def update_policy(policy_id: int, payload: PolicyPayload, request: Request, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    require_admin(actor)
    before = engine.get_policy(db, policy_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    _check(db, payload)
    engine.save_policy(db, policy_id, name=payload.name, description=payload.description, enabled=payload.enabled,
                       condition=payload.condition, actions=payload.actions.model_dump(), by=actor.display_name)
    if not payload.enabled or not payload.actions.alert:
        # Disabled, or no alert any more: what it opened closes
        if payload.enabled:
            engine._resolve_alerts(db, policy_id)
        else:
            engine.forget_policy(db, policy_id)
        db.commit()
    _audit(db, request, "policy.updated", policy_id, payload.name,
           {"before": {k: before[k] for k in ("name", "enabled", "condition", "actions")}, "condition": payload.condition, "actions": payload.actions.model_dump(), "enabled": payload.enabled})
    summary = await engine.run_all_and_dispatch(db, policy_id=policy_id, trigger="admin") if payload.enabled else None
    return ui_data({"policy": engine.get_policy(db, policy_id), "run": summary})


@router.delete("/{policy_id}")
def delete_policy(policy_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(actor_from_request(request))
    policy = engine.get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    engine.delete_policy(db, policy_id)
    _audit(db, request, "policy.deleted", policy_id, policy["name"], {"condition": policy["condition"]})
    return ui_data({"deleted": int(policy_id)})


@router.post("/{policy_id}/run")
async def run_policy(policy_id: int, request: Request, db: Session = Depends(get_db)):
    require_admin(actor_from_request(request))
    policy = engine.get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    if not policy["enabled"]:
        raise HTTPException(status_code=409, detail={"code": "POLICY_DISABLED", "message": "Cette politique est désactivée"})
    summary = await engine.run_all_and_dispatch(db, policy_id=policy_id, trigger="admin")
    _audit(db, request, "policy.run", policy_id, policy["name"], {"results": summary.get("results")})
    return ui_data({"policy": engine.get_policy(db, policy_id), "run": summary})
