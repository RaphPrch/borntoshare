from __future__ import annotations

from fastapi import APIRouter

# Core
from app.api.internal import router as internal_router
from app.api.zones import router as zones_router
from app.api.tags import router as tags_router
from app.api.storage_endpoints import router as storage_endpoints_router
from app.api.storage_roots import router as storage_roots_router
from app.api.access_requests import internal_router as access_requests_internal_router
from app.api.access_requests import router as access_requests_router

# Directory / bindings / misc
from app.api.activity_views import router as activity_views_router
from app.api.dashboard import router as dashboard_router
from app.api.advanced_settings import router as advanced_settings_router
from app.api.naming_policies import router as naming_policies_router
from app.api.infrastructure import router as infrastructure_router
from app.api.observability import router as observability_router
from app.api.internal_sso import router as internal_sso_router
from app.api.governance_alerts import router as governance_alerts_router
from app.api.health_events import router as health_events_router

# Identity sources (AD / OIDC connectors)
from app.api.identity_sources import router as identity_sources_router
from app.api.internal_identity_sources import router as internal_identity_sources_router
from app.api.internal_secrets import router as internal_secrets_router
from app.api.internal_identity_roles import router as internal_identity_roles_router
from app.api.internal_identities import router as internal_identities_router
from app.api.provisioning_internal import router as provisioning_internal_router
from app.api.internal_directory_snapshots import router as internal_directory_snapshots_router
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
router.include_router(dashboard_router)
router.include_router(advanced_settings_router)
router.include_router(naming_policies_router)
router.include_router(infrastructure_router)
router.include_router(observability_router)
router.include_router(internal_sso_router)
router.include_router(governance_alerts_router)
router.include_router(health_events_router)


# Directory / bindings / misc
# Identity sources
router.include_router(identity_sources_router)
router.include_router(internal_identity_sources_router)
router.include_router(internal_secrets_router)
router.include_router(internal_identity_roles_router)
router.include_router(internal_identities_router)
router.include_router(provisioning_internal_router)
router.include_router(internal_directory_snapshots_router)
router.include_router(identity_list_router)
