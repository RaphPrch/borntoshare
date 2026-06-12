from __future__ import annotations

import pytest

from app.shared.b2s_job_contracts.actors import publish_job
from app.shared.b2s_job_contracts.contracts import (
    JOB_CONTRACTS,
    actor_for_job_type,
    default_action_for_job_type,
    queue_for_job_type,
    queue_job_types_csv,
)


def test_job_contracts_route_probe_and_identity_jobs_to_expected_queues() -> None:
    assert queue_for_job_type("LDAP_TEST") == "capsule_identity"
    assert queue_for_job_type("IDENTITY_SEARCH") == "capsule_identity"
    assert queue_for_job_type("SMB_PROBE") == "capsule_probes"
    assert queue_for_job_type("ACL_APPLY") == "capsule_acl"


def test_job_contracts_keep_actor_and_default_action_consistent() -> None:
    assert actor_for_job_type("LDAP_TEST") == "run_identity_job"
    assert actor_for_job_type("SMB_PROBE") == "run_probe_job"
    assert actor_for_job_type("ACL_APPLY") == "run_acl_job"
    assert default_action_for_job_type("AD_GROUP_ENSURE") == "ensure_ad_group"
    assert queue_job_types_csv() == ",".join(sorted(JOB_CONTRACTS))


def test_job_contracts_reject_unknown_job_type_before_enqueue() -> None:
    with pytest.raises(ValueError, match="Unsupported job_type: UNKNOWN_JOB"):
        publish_job("UNKNOWN_JOB", 123)
