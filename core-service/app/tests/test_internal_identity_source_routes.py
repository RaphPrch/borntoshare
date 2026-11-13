"""« /internal/identity-sources/active » was taken by « /{source_id} » (422): the directory sign-in without a
domain and the « Directory » tab of the sign-in page rely on it."""
from __future__ import annotations

from app.api.internal_identity_sources import router


def _match(path: str) -> str:
    from starlette.routing import Match

    scope = {"type": "http", "path": path, "method": "GET", "root_path": ""}
    for route in router.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return route.path
    return ""


def test_active_is_not_an_identity_source_id() -> None:
    assert _match(f"{router.prefix}/active").endswith("/active")
    assert _match(f"{router.prefix}/12").endswith("/{source_id:int}")
