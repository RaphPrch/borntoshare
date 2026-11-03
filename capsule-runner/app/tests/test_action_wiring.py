"""Every worker action is declared in all the places that run it: registry, scope guard and job contracts."""
from __future__ import annotations

from app.core.action_registry import ALLOWED_ACTIONS
from app.core.scope_guard import ACTION_MIN_SCOPE
from app.shared.b2s_job_contracts.contracts import JOB_CONTRACTS


def test_every_action_has_its_scope_and_every_scope_its_action() -> None:
    assert sorted(set(ALLOWED_ACTIONS) - set(ACTION_MIN_SCOPE)) == []
    assert sorted(set(ACTION_MIN_SCOPE) - set(ALLOWED_ACTIONS)) == []


def test_every_action_is_registered_under_its_own_name() -> None:
    assert [slug for slug, spec in ALLOWED_ACTIONS.items() if spec.action != slug] == []


def test_the_default_action_of_every_job_type_exists() -> None:
    assert sorted({c.default_action for c in JOB_CONTRACTS.values()} - set(ALLOWED_ACTIONS)) == []
