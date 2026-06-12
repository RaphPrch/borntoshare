from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.repositories.tags_views_repo import TagsViewsRepo
from app.routers._helpers import ui_action, ui_data, ui_list
from app.schemas.tag import TagCreate, TagUpdate
from app.models.tag import Tag
from app.schemas.tag_attachment import TagAttachmentRequest
from app.models.storage_root_tag import storage_root_tag
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request

router = APIRouter(prefix="/tags", tags=["tags"])


def _actor_from_headers(request: Request) -> tuple[int | None, str | None]:
    actor = actor_from_request(request)
    return actor.identity_id, actor.display_name


# ============================================================
# READ MODELS (Views)
# ============================================================

@router.get("")
def list_tags(db: Session = Depends(get_db)):
    """List tags (read-model).

    Backed by table: tags
    """
    rows = TagsViewsRepo(db).list()
    return ui_list([dict(r) for r in rows])


# ============================================================
# WRITE MODELS — TAG CRUD
# ============================================================

@router.post("", status_code=status.HTTP_201_CREATED)
def create_tag(payload: TagCreate, request: Request, db: Session = Depends(get_db)):
    tag = Tag(
        name=payload.name,
        color=payload.color,
    )

    db.add(tag)
    db.commit()
    db.refresh(tag)

    actor_id, actor_display = _actor_from_headers(request)
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="tag.created",
        outcome="success",
        target_type="tag",
        target_id=int(tag.id),
        target_display=str(tag.name or tag.id),
        context_json={"name": tag.name, "color": tag.color},
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_data(
        {
            "id": int(tag.id),
            "name": tag.name,
            "color": tag.color,
        },
        meta={"tag_id": int(tag.id)},
    )


@router.patch("/{tag_id}")
def update_tag(tag_id: int, payload: TagUpdate, request: Request, db: Session = Depends(get_db)):
    tag: Tag | None = db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")

    before = {"name": tag.name, "color": tag.color}
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(tag, key, value)

    db.commit()
    db.refresh(tag)

    after = {"name": tag.name, "color": tag.color}
    actor_id, actor_display = _actor_from_headers(request)
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="tag.updated",
        outcome="success",
        target_type="tag",
        target_id=int(tag.id),
        target_display=str(tag.name or tag.id),
        context_json={"before": before, "after": after, "updated_fields": sorted(list(data.keys()))},
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_data(
        {
            "id": int(tag.id),
            "name": tag.name,
            "color": tag.color,
        },
        meta={"tag_id": int(tag.id)},
    )


@router.delete("/{tag_id}")
def delete_tag(tag_id: int, request: Request, db: Session = Depends(get_db)):
    tag: Tag | None = db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")

    has_root = db.execute(
        select(storage_root_tag.c.tag_id).where(storage_root_tag.c.tag_id == tag_id).limit(1)
    ).first()
    if has_root:
        raise HTTPException(
            status_code=409,
            detail="Tag is still attached to resources",
        )

    target_display = str(tag.name or tag.id)
    context = {"name": tag.name, "color": tag.color}
    db.delete(tag)
    db.commit()

    actor_id, actor_display = _actor_from_headers(request)
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="tag.deleted",
        outcome="success",
        target_type="tag",
        target_id=int(tag_id),
        target_display=target_display,
        context_json=context,
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_action(action_id=int(tag_id), message="tag.deleted")


# ============================================================
# WRITE MODELS — TAG ATTACHMENT
# ============================================================

_RESOURCE_TABLES = {
    "storage_root": storage_root_tag,
}


@router.post("/attach", status_code=status.HTTP_201_CREATED)
def attach_tag(payload: TagAttachmentRequest, request: Request, db: Session = Depends(get_db)):
    table = _RESOURCE_TABLES.get(payload.resource_type)
    if table is None:
        raise HTTPException(status_code=400, detail="Unsupported resource_type")

    # Column naming depends on resource
    resource_col = f"{payload.resource_type}_id"

    already_attached = False
    try:
        db.execute(
            table.insert().values(
                {
                    resource_col: int(payload.resource_id),
                    "tag_id": int(payload.tag_id),
                }
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        message = str(getattr(exc, "orig", exc))
        # Idempotent behavior on duplicate association.
        if "Duplicate entry" in message or "uq_storage_root_tags_storage_root_id_tag_id" in message:
            already_attached = True
        else:
            raise HTTPException(status_code=409, detail="Tag attachment failed") from exc

    actor_id, actor_display = _actor_from_headers(request)
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="tag.attached",
        outcome="success",
        target_type=str(payload.resource_type),
        target_id=int(payload.resource_id),
        target_display=f"{payload.resource_type}:{payload.resource_id}",
        context_json={"tag_id": int(payload.tag_id), "already_attached": already_attached},
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_action(
        action_id=int(payload.tag_id),
        message="tag.attached",
        details={
            "resource_type": str(payload.resource_type),
            "resource_id": int(payload.resource_id),
            "already_attached": bool(already_attached),
        },
    )


@router.post("/detach", status_code=status.HTTP_200_OK)
def detach_tag(payload: TagAttachmentRequest, request: Request, db: Session = Depends(get_db)):
    table = _RESOURCE_TABLES.get(payload.resource_type)
    if table is None:
        raise HTTPException(status_code=400, detail="Unsupported resource_type")

    resource_col = f"{payload.resource_type}_id"

    db.execute(
        table.delete().where(
            (table.c[resource_col] == int(payload.resource_id))
            & (table.c.tag_id == int(payload.tag_id))
        )
    )
    db.commit()

    actor_id, actor_display = _actor_from_headers(request)
    log_activity(
        db,
        actor_type="user" if actor_id is not None else "system",
        actor_id=actor_id,
        actor_display=actor_display,
        action="tag.detached",
        outcome="success",
        target_type=str(payload.resource_type),
        target_id=int(payload.resource_id),
        target_display=f"{payload.resource_type}:{payload.resource_id}",
        context_json={"tag_id": int(payload.tag_id)},
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_action(
        action_id=int(payload.tag_id),
        message="tag.detached",
        details={
            "resource_type": str(payload.resource_type),
            "resource_id": int(payload.resource_id),
        },
    )
