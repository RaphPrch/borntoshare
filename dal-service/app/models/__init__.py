"""
BornToShare (B2S) — SQLAlchemy Models Registry
GOLD / V2-ready

CRITICAL RULES:
- Import order MATTERS
- Association tables MUST be imported before ORM models
- This file is the single source of truth for model registration
- No Alembic: schema is managed manually
"""

# ============================================================
# Base
# ============================================================
from .base import Base  # noqa: F401


# ============================================================
# Association tables (NO ORM models)
# MUST be imported before models using them
# ============================================================
from .storage_root_tag import storage_root_tag  # noqa: F401


# ============================================================
# Identity & Authentication
# ============================================================
from .identity import Identity  # noqa: F401
from .local_credential import LocalCredential  # noqa: F401
from .identity_sources import IdentitySource  # noqa: F401
from .directory_snapshot import DirectorySnapshot  # noqa: F401
from .directory_snapshot_user import DirectorySnapshotUser  # noqa: F401
from .directory_snapshot_group import DirectorySnapshotGroup  # noqa: F401
from .directory_snapshot_membership import DirectorySnapshotMembership  # noqa: F401
from .directory_effective_membership import DirectoryEffectiveMembership  # noqa: F401



# ============================================================
# Platform topology
# ============================================================
from .zone import Zone  # noqa: F401
from .zone_provisioning_policy import ZoneProvisioningPolicy  # noqa: F401
from .zone_access_profile import ZoneAccessProfile  # noqa: F401


# ============================================================
# Storage
# ============================================================
from .storage_endpoint import StorageEndpoint  # noqa: F401
from .storage_root import StorageRoot  # noqa: F401
from .storage_root_role import StorageRootRole  # noqa: F401


# ============================================================
# Governance
# ============================================================
from .tag import Tag  # noqa: F401
from .governance_health_event import GovernanceHealthEvent  # noqa: F401


# ============================================================
# Access Management
# ============================================================
from .access_profile import AccessProfile  # noqa: F401
from .access_request import AccessRequest  # noqa: F401
from .access_request_item import AccessRequestItem  # noqa: F401
from .access_request_item_execution import AccessRequestItemExecution  # noqa: F401
from .storage_root_access_profile import StorageRootAccessProfile  # noqa: F401
from .provisioning_job import ProvisioningJob  # noqa: F401


# ============================================================
# Audit / Observability
# ============================================================
# from .audit_event import AuditEvent  # noqa: F401
