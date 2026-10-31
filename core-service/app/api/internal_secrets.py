from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.core.internal_auth import require_internal_token
from app.services import secret_store

router = APIRouter(
    prefix="/internal/secrets",
    tags=["internal-secrets"],
    dependencies=[Depends(require_internal_token)],
)

_HTTP_STATUS = {
    secret_store.SecretInvalidRef: status.HTTP_400_BAD_REQUEST,
    secret_store.SecretNotFound: status.HTTP_404_NOT_FOUND,
    secret_store.SecretDecryptFailed: status.HTTP_409_CONFLICT,
}


def _refuse(exc: secret_store.SecretError) -> HTTPException:
    return HTTPException(
        status_code=_HTTP_STATUS.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR),
        detail={"code": exc.code, "message": str(exc)},
    )


class StoreSecretIn(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    value: str = Field(min_length=1)


class SecretRefIn(BaseModel):
    ref: str = Field(min_length=1, max_length=512)


@router.post("/store")
def store_secret(payload: StoreSecretIn, db: Session = Depends(get_db)):
    try:
        return ui_data({"ref": secret_store.store(db, payload.name, payload.value)})
    except secret_store.SecretError as exc:
        raise _refuse(exc) from exc


@router.post("/resolve")
def resolve_secret(payload: SecretRefIn, db: Session = Depends(get_db)):
    try:
        return ui_data({"value": secret_store.resolve(db, payload.ref)})
    except secret_store.SecretError as exc:
        raise _refuse(exc) from exc
