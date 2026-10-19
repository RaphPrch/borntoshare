"""Call a route handler directly (same process, no HTTP), for orchestration code.

The handler runs with its own DB session, like a request would; the result has the
same JSON shape a client would get, and HTTPException propagates unchanged.
"""
from __future__ import annotations

import inspect
from typing import Any, Callable, get_type_hints

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.params import Depends as DependsParam
from fastapi.params import Param, Body
from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticUndefined

from app.core.db import SessionLocal


def _bind_arguments(handler: Callable[..., Any], db: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    bound: dict[str, Any] = {}
    hints = get_type_hints(handler)  # resolves string annotations (from __future__ import annotations)
    for name, param in inspect.signature(handler).parameters.items():
        if name == "db":
            bound[name] = db
            continue
        value = kwargs.pop(name, PydanticUndefined)
        default = param.default
        if value is PydanticUndefined:
            # Query(...)/Body(...) defaults are FastAPI markers: use the value they carry.
            if isinstance(default, (Param, Body)):
                value = default.default
            elif isinstance(default, DependsParam) or default is inspect.Parameter.empty:
                raise TypeError(f"{handler.__name__}() missing argument {name!r}")
            else:
                value = default
            if value is PydanticUndefined:
                raise TypeError(f"{handler.__name__}() missing argument {name!r}")
        annotation = hints.get(name)
        if isinstance(annotation, type) and issubclass(annotation, BaseModel) and isinstance(value, dict):
            try:
                value = annotation.model_validate(value)
            except ValidationError as exc:
                raise HTTPException(status_code=422, detail={"errors": exc.errors(include_url=False)}) from exc
        bound[name] = value
    if kwargs:
        raise TypeError(f"{handler.__name__}() got unexpected arguments {sorted(kwargs)}")
    return bound


async def call_route(handler: Callable[..., Any], /, **kwargs: Any) -> Any:
    """Run `handler` with the given arguments (dict payloads are validated into the handler's model)."""
    db = SessionLocal()
    try:
        arguments = _bind_arguments(handler, db, dict(kwargs))
        if inspect.iscoroutinefunction(handler):
            result = await handler(**arguments)
        else:
            result = await run_in_threadpool(handler, **arguments)
        return jsonable_encoder(result)
    finally:
        db.close()
