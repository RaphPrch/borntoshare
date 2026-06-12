from __future__ import annotations

from fastapi import APIRouter

# Core
from app.routers.internal import router as internal_router
from app.routers.zones import router as zones_router
from app.routers.tags import router as tags_router
from app.routers.storage_endpoints import router as storage_endpoints_router
from app.routers.storage_roots import router as storage_roots_router
from app.routers.access_requests import internal_router as access_requests_internal_router
from app.routers.access_requests import router as access_requests_router

# Directory / bindings / misc
from app.routers.access_profiles import router as access_profiles_router
from app.routers.activity_views import router as activity_views_router
from app.routers.activity_events import router as activity_events_router
from app.routers.dashboard import router as dashboard_router
from app.routers.advanced_settings import router as advanced_settings_router
from app.routers.naming_policies import router as naming_policies_router
from app.routers.governance_alerts import router as governance_alerts_router
from app.routers.health_events import router as health_events_router

# Identity sources (AD / OIDC connectors)
from app.routers.identity_sources import router as identity_sources_router
from app.routers.internal_identity_sources import router as internal_identity_sources_router
from app.routers.internal_identity_roles import router as internal_identity_roles_router
from app.routers.internal_identities import router as internal_identities_router
from app.routers.provisioning_internal import router as provisioning_internal_router
from app.routers.internal_directory_snapshots import router as internal_directory_snapshots_router
from app.routers.storage_root_bindings_internal import router as storage_root_bindings_internal_router
from .identity_list import router as identity_list_router



router = APIRouter()

# Core
router.include_router(internal_router)
router.include_router(zones_router)
router.include_router(tags_router)
router.include_router(storage_endpoints_router)
router.include_router(storage_roots_router)
router.include_router(access_requests_router)
router.include_router(access_requests_internal_router)

router.include_router(activity_views_router)
router.include_router(activity_events_router)
router.include_router(dashboard_router)
router.include_router(advanced_settings_router)
router.include_router(naming_policies_router)
router.include_router(governance_alerts_router)
router.include_router(health_events_router)


# Directory / bindings / misc
router.include_router(access_profiles_router)
# Identity sources
router.include_router(identity_sources_router)
router.include_router(internal_identity_sources_router)
router.include_router(internal_identity_roles_router)
router.include_router(internal_identities_router)
router.include_router(provisioning_internal_router)
router.include_router(internal_directory_snapshots_router)
router.include_router(storage_root_bindings_internal_router)
router.include_router(identity_list_router)
