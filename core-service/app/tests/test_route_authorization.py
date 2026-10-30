"""Write routes must carry their authorization: nothing relies on the frontend BFF alone."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import (
    activity_events,
    activity_views,
    advanced_settings,
    health_events,
    identity_list,
    identity_sources,
    naming_policies,
    storage_roots,
    zones,
)
from app.api.governance import identity_orchestration, probes, provisioning
from app.services.authorization import (
    admin_only,
    admin_or_guardian,
    admin_or_internal,
    own_root_of_probe,
    probe_job_of_own_root,
    probe_of_own_root,
    signed_in_or_internal,
    stamp_actor,
)


def _request(**headers: str) -> Request:
    raw = [(key.replace("_", "-").encode(), value.encode()) for key, value in headers.items()]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": raw, "query_string": b""})


GUARDED = [
    (zones, ["create_zone", "update_zone", "delete_zone", "put_zone_provisioning_policy"], admin_or_internal),
    (identity_sources, ["create_identity_source", "update_identity_source", "delete_identity_source"], admin_or_internal),
    (identity_list, ["create_identity", "update_identity", "delete_identity"], admin_or_internal),
    (naming_policies, ["preview_group_name", "preview_root_groups"], admin_or_internal),
    (advanced_settings, ["save_advanced_config"], admin_or_internal),
    (storage_roots, ["create_root", "delete_root", "sync_storage_root_discovery"], admin_only),
    (activity_views, ["post_activity_event"], signed_in_or_internal),
    (activity_events, ["create_activity_event_route"], signed_in_or_internal),
    (provisioning, ["cancel_admin_job"], admin_only),
    (probes, ["run_probe", "get_probe_job"], admin_or_guardian),
    (probes, ["run_probe"], probe_of_own_root),
    (probes, ["get_probe_job"], probe_job_of_own_root),
    (provisioning, ["list_admin_jobs"], admin_only),
    (zones, ["list_zones", "get_zone", "get_zone_console", "get_zone_provisioning_policy"], admin_or_internal),
    (identity_sources, ["list_identity_sources", "get_identity_source_internal"], admin_or_internal),
    (identity_list, ["list_identity_overview", "list_identity_group_members"], admin_or_internal),
    (naming_policies, ["get_global_naming_policy", "get_zone_naming_policy"], admin_or_internal),
    (advanced_settings, ["get_advanced_config"], admin_or_internal),
    (health_events, ["get_health_summary"], admin_or_internal),
    (identity_orchestration, ["run_identity_snapshot", "update_identity", "discover_identity"], admin_only),
    (identity_orchestration, ["import_identity_ad", "import_identity_ad_batch"], admin_or_guardian),
    (identity_orchestration, ["search_identity"], signed_in_or_internal),
]


@pytest.mark.parametrize("module,names,guard", GUARDED)
def test_route_carries_its_guard(module, names, guard):
    for name in names:
        routes = [r for r in module.router.routes if getattr(r, "endpoint", None) is getattr(module, name)]
        assert routes, f"{name}: route not found"
        calls = [dep.call for dep in routes[0].dependant.dependencies]
        assert guard in calls, f"{name} is not guarded by {guard.__name__}"


def test_admin_only_refuses_everyone_else():
    admin_only(_request(x_roles="platform_admin"))
    with pytest.raises(HTTPException) as exc:
        admin_only(_request(x_roles="user", x_identity_id="5"))
    assert exc.value.status_code == 403


def test_admin_or_internal_refuses_a_user_without_token():
    admin_or_internal(_request(x_roles="platform_admin"))
    with pytest.raises(HTTPException) as exc:
        admin_or_internal(_request(x_roles="user", x_identity_id="5"))
    assert exc.value.status_code == 403


def test_signed_in_or_internal_refuses_an_anonymous_call():
    signed_in_or_internal(_request(x_identity_id="5"))
    with pytest.raises(HTTPException) as exc:
        signed_in_or_internal(_request())
    assert exc.value.status_code == 403


def test_stamp_actor_ignores_the_actor_of_the_payload():
    forged = {"action": "x", "actor_type": "system", "actor_id": "admin", "actor_display": "admin"}
    stamped = stamp_actor(_request(x_identity_id="5", x_actor_display="Claire"), forged)
    assert (stamped["actor_type"], stamped["actor_id"], stamped["actor_display"]) == ("user", 5, "Claire")
    # A service with the internal token keeps what it declares
    assert stamp_actor(_request(), forged) == forged


@pytest.mark.parametrize(
    "body,expected",
    [
        ({"kind": "storage-root", "target": {"storage_root_id": 7}}, 7),
        ({"kind": "storage-endpoint", "target": {"storage_root_id": 7}}, None),
        ({"kind": "storage-root", "target": {"storage_root_id": 7, "host": "elsewhere.example.test"}}, None),
        ({"kind": "storage-root", "target": {"storage_root_id": 7}, "auth": {"username": "x"}}, None),
        ({"kind": "storage-root", "target": {}}, None),
    ],
)
def test_guardian_only_probes_a_root_by_id(body, expected):
    assert own_root_of_probe(body) == expected
