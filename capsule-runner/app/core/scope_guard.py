from __future__ import annotations

from app.core import settings
from app.core.action_registry import CapsuleActionError


_RANK = {
    "read": 1,
    "write": 2,
}


ACTION_MIN_SCOPE: dict[str, str] = {
    # Read-only probes/search
    "infra_health_check": "read",
    "test_smb_ntlm": "read",
    "test_smb_root_access": "read",
    "test_ldap": "read",
    "test_ldaps": "read",
    "fetch_tls_certificate": "read",
    "discover_directory": "read",
    "discover_smb_server": "read",
    "read_dfs_namespaces": "read",
    "resolve_name": "read",
    "search_ldap_principals": "read",
    "search_ldaps_principals": "read",
    "test_kerberos": "read",
    "collect_directory_snapshot": "read",
    "discover_group_users_recursive": "read",
    # Mutations
    "ensure_ad_group": "write",
    "ensure_ad_group_member": "write",
    "remove_ad_group_member": "write",
    "grant_ad_access": "write",
    "acl_apply_via_group": "write",
    "folder_inheritance": "write",
    "folder_delete": "write",
    "folder_create": "write",
    "folder_list": "read",
    "share_create": "write",
    "share_delete": "write",
    "dfs_folder_create": "write",
    "dfs_folder_delete": "write",
}


def ensure_action_scope_allowed(action: str) -> None:
    normalized_action = str(action or "").strip()
    if not normalized_action:
        raise CapsuleActionError(
            error_code="CAPSULE_SCOPE_DENIED",
            message="action is required",
            retryable=False,
        )

    runner_scope = str(settings.RUNNER_MAX_SCOPE or "write").strip().lower()
    required_scope = ACTION_MIN_SCOPE.get(normalized_action)
    if required_scope is None:
        # An action without a declared scope never runs
        raise CapsuleActionError(
            error_code="CAPSULE_SCOPE_DENIED",
            message=f"Action '{normalized_action}' has no declared scope",
            retryable=False,
        )

    if _RANK.get(runner_scope, 0) < _RANK[required_scope]:
        raise CapsuleActionError(
            error_code="CAPSULE_SCOPE_DENIED",
            message=f"Action '{normalized_action}' requires scope '{required_scope}' (runner max: '{runner_scope}')",
            retryable=False,
        )
