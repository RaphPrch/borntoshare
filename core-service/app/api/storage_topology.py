"""Storage topology (Administration › Storage Endpoints › Topology): zones, servers, volumes, shares, DFS namespaces
and governed folders, with their state. Administrators only: it shows the hosts of the servers and their probe messages."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.services.authorization import admin_only
from app.services.storage_topology import StorageTopology

router = APIRouter(prefix="/storage-topology", tags=["storage-topology"], dependencies=[Depends(admin_only)])


def _found(value):
    if value is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return value


@router.get("")
def overview(db: Session = Depends(get_db)):
    """Every zone with its servers and DFS namespaces, counted (no folder is loaded)."""
    return ui_data(StorageTopology(db).overview())


@router.get("/servers/{endpoint_id}")
def server(endpoint_id: int, db: Session = Depends(get_db)):
    """A server: its volumes (when an FSRM reading gave them) and its shares, counted."""
    return ui_data(_found(StorageTopology(db).server(endpoint_id)))


@router.get("/servers/{endpoint_id}/roots")
def server_roots(
    endpoint_id: int,
    share: str | None = Query(None, max_length=1024),
    volume: str | None = Query(None, pattern=r"^[A-Za-z]:?$"),
    state: Literal["available", "unavailable", "unknown", "stale"] | None = None,
    q: str | None = Query(None, max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """The governed folders of a server, a share or a volume, page by page."""
    return ui_data(StorageTopology(db).roots(endpoint_id, share=share, volume=volume, state=state, q=q, offset=offset, limit=limit))


@router.get("/dfs/{endpoint_id}")
def dfs(
    endpoint_id: int,
    q: str | None = Query(None, max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """A DFS namespace: its folders and the governed folders they lead to, page by page."""
    return ui_data(_found(StorageTopology(db).dfs(endpoint_id, offset=offset, limit=limit, q=q)))
