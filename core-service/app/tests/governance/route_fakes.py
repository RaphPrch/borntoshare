"""Test helper: keep path-based fakes for orchestration code that calls route handlers directly.

`fake_routes(monkeypatch, module, get=..., post=...)` replaces `module.call_route` with a fake
that turns `call_route(handler, **kwargs)` back into the route's path (and payload), then
delegates to the given `get(path)` / `post(path, payload)` / `patch(path, payload)` fakes.
"""
from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlencode

from app.api import (
    access_requests,
    identity_list,
    identity_sources,
    internal_directory_snapshots,
    internal_identities,
    naming_policies,
    provisioning_internal,
)
from app.services import provisioning_jobs

_P = "/api/internal/provisioning"

ROUTES: dict[Callable[..., Any], tuple[str, str]] = {
    provisioning_internal.get_storage_root_provisioning_context: ("GET", _P + "/storage-roots/{storage_root_id}/context"),
    provisioning_internal.ensure_storage_root_access_group: ("POST", _P + "/storage-root-access-profiles"),
    provisioning_internal.list_storage_root_access_profiles: ("GET", _P + "/storage-root-access-profiles"),
    provisioning_internal.create_provisioning_job: ("POST", _P + "/jobs"),
    provisioning_internal.list_provisioning_jobs: ("GET", _P + "/jobs"),
    provisioning_internal.get_provisioning_job_by_id: ("GET", _P + "/jobs/{job_id}"),
    provisioning_internal.cancel_provisioning_job: ("POST", _P + "/jobs/{job_id}/cancel"),
    provisioning_internal.mark_watchdog_republish: ("POST", _P + "/jobs/{job_id}/watchdog-republish-mark"),
    provisioning_internal.complete_provisioning_job: ("POST", _P + "/jobs/{job_id}/complete"),
    provisioning_internal.fail_provisioning_job: ("POST", _P + "/jobs/{job_id}/fail"),
    access_requests.get_access_request_provisioning_plan_internal: (
        "GET",
        "/api/internal/access-requests/{access_request_id}/provisioning-plan",
    ),
    access_requests.create_access_request_item_execution_internal: ("POST", "/api/internal/access-requests/item-executions"),
    access_requests.other_active_request_for_level: (
        "GET",
        "/api/internal/access-requests/{access_request_id}/other-active",
    ),
    access_requests.bulk_decision: ("POST", "/api/access-requests/bulk"),
    internal_directory_snapshots.create_snapshot_run: ("POST", "/api/internal/directory-snapshots/runs"),
    internal_directory_snapshots.list_snapshot_runs: ("GET", "/api/internal/directory-snapshots/runs"),
    internal_directory_snapshots.search_snapshot_principals: (
        "GET",
        "/api/internal/directory-snapshots/runs/{snapshot_id}/search",
    ),
    internal_identities.resolve_ad_identity: ("POST", "/api/internal/identities/resolve-ad"),
    internal_identities.resolve_ad_identity_batch: ("POST", "/api/internal/identities/resolve-ad/batch"),
    naming_policies.preview_group_name: ("POST", "/api/naming-policies/preview"),
    identity_list.list_identity_overview: ("GET", "/api/identity"),
    identity_list.update_identity: ("PATCH", "/api/identity/{identity_id}"),
    identity_sources.list_identity_sources: ("GET", "/api/identity-sources"),
    identity_sources.get_identity_source_internal: ("GET", "/api/identity-sources/{source_id}/internal"),
}

# Python argument name -> query string name, where they differ
_QUERY_ALIASES = {"status_value": "status"}


def route_path(handler: Callable[..., Any], kwargs: dict[str, Any]) -> tuple[str, str, Any]:
    method, template = ROUTES[handler]
    args = dict(kwargs)
    args.pop("request", None)
    payload = args.pop("payload", None)
    path = template
    for name in list(args):
        if "{" + name + "}" in path:
            path = path.replace("{" + name + "}", str(args.pop(name)))
    query = {
        _QUERY_ALIASES.get(name, name): (str(value).lower() if isinstance(value, bool) else value)
        for name, value in args.items()
        if value is not None and value != ""
    }
    if query:
        path = f"{path}?{urlencode(query)}"
    return method, path, payload


class PathFakes:
    def __init__(self) -> None:
        self.fakes: dict[str, Callable[..., Any]] = {}
        self.requests: list[Any] = []  # `request` forwarded to handlers that need the caller's headers

    async def __call__(self, handler: Callable[..., Any], /, **kwargs: Any) -> Any:
        if "request" in kwargs:
            self.requests.append(kwargs["request"])
        method, path, payload = route_path(handler, kwargs)
        fake = self.fakes.get(method)
        if fake is None:
            raise AssertionError(f"unexpected {method} {path}")
        if method == "GET":
            return await fake(path)
        return await fake(path, dict(payload or {}))


def fake_routes(monkeypatch, module, *, get=None, post=None, patch=None) -> PathFakes:
    """Fake `module.call_route`, and the job creation it triggers (services.provisioning_jobs)."""
    current = getattr(module, "call_route", None)
    fakes = current if isinstance(current, PathFakes) else PathFakes()
    for method, fake in (("GET", get), ("POST", post), ("PATCH", patch)):
        if fake is not None:
            fakes.fakes[method] = fake
    monkeypatch.setattr(module, "call_route", fakes)
    if module is not provisioning_jobs and not isinstance(provisioning_jobs.call_route, PathFakes):
        monkeypatch.setattr(provisioning_jobs, "call_route", fakes)
    return fakes
