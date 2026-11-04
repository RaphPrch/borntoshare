"""The core sends only jobs the worker knows: every template has its job type, every job type its contract,
every template an action of the worker, and the two copies of the job contracts stay the same."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.jobs.b2s_job_contracts.contracts import JOB_CONTRACTS
from app.services import probe_service

REPO = Path(__file__).resolve().parents[3]
WORKER_REGISTRY = REPO / "capsule-runner" / "app" / "core" / "action_registry.py"
WORKER_CONTRACTS = REPO / "capsule-runner" / "app" / "shared" / "b2s_job_contracts" / "contracts.py"
CORE_CONTRACTS = Path(probe_service.__file__).resolve().parents[1] / "jobs" / "b2s_job_contracts" / "contracts.py"


def _templates() -> set[str]:
    source = Path(probe_service.__file__).read_text(encoding="utf-8")
    return set(re.findall(r'return "([a-z_]+)", "v1"', source))


def test_every_template_has_a_job_type_with_a_contract() -> None:
    mapping = probe_service._PROBE_JOB_TYPE_BY_TEMPLATE
    assert len(_templates()) >= 10, "the templates are no longer found in probe_service"
    assert sorted(_templates() - set(mapping)) == []
    assert sorted(set(mapping.values()) - set(JOB_CONTRACTS)) == []


@pytest.mark.skipif(not WORKER_REGISTRY.exists(), reason="the worker is not next to the core (image build)")
def test_every_template_is_an_action_of_the_worker() -> None:
    actions = set(re.findall(r'^    "([a-z_]+)": ActionSpec\(', WORKER_REGISTRY.read_text(encoding="utf-8"), re.M))
    assert len(actions) >= 10, "the actions are no longer found in the worker registry"
    assert sorted((_templates() | set(probe_service._PROBE_JOB_TYPE_BY_TEMPLATE)) - actions) == []


@pytest.mark.skipif(not WORKER_CONTRACTS.exists(), reason="the worker is not next to the core (image build)")
def test_the_two_copies_of_the_job_contracts_are_the_same() -> None:
    assert CORE_CONTRACTS.read_text(encoding="utf-8") == WORKER_CONTRACTS.read_text(encoding="utf-8")


WORKER_NAMES = REPO / "capsule-runner" / "app" / "shared" / "windows_names.py"
CORE_NAMES = Path(probe_service.__file__).resolve().parent / "windows_names.py"


@pytest.mark.skipif(not WORKER_NAMES.exists(), reason="the worker is not next to the core (image build)")
def test_the_two_copies_of_the_windows_name_rules_are_the_same() -> None:
    assert CORE_NAMES.read_text(encoding="utf-8") == WORKER_NAMES.read_text(encoding="utf-8")


TEMPLATES = REPO / "frontend-service" / "src" / "lib" / "activity" / "templates.ts"
EVENT = re.compile(
    r'"((?:zone|storage_endpoint|storage_root|access_request|identity_source|identity|tag|infrastructure|advanced_settings'
    r'|governance_alert|logs|naming_policy|job|request|extension)\.[a-z_]+)"'
)
# Written through f"infrastructure.{task}_run": one per scheduled task
SCHEDULED_TASKS = ("health_check", "data_sync", "access_expiry", "dfs_read")


@pytest.mark.skipif(not TEMPLATES.exists(), reason="the frontend is not next to the core (image build)")
def test_every_audited_event_has_a_wording_in_the_activity() -> None:
    core = Path(probe_service.__file__).resolve().parents[1]
    written = {
        match
        for path in core.rglob("*.py")
        if "tests" not in path.parts
        for match in EVENT.findall(path.read_text(encoding="utf-8"))
    } | {f"infrastructure.{task}_run" for task in SCHEDULED_TASKS}
    templates = set(re.findall(r"^  '([a-z_]+\.[a-z_.]+)':", TEMPLATES.read_text(encoding="utf-8"), re.M))
    assert len(written) >= 40 and len(templates) >= 40
    assert sorted(written - templates) == []
