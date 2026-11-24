"""Files copied on purpose in several services (each image stays self-contained) must stay identical.

The worker contract (contracts.py), the Windows name rules and the secret-file reader exist once per service that needs
them; this test fails as soon as one copy changes without the others. actors.py is not checked: the core enqueues,
the worker consumes, the two files differ by design.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
COPIES = {
    "worker contract": ["core-service/app/jobs/b2s_job_contracts/contracts.py", "capsule-runner/app/shared/b2s_job_contracts/contracts.py"],
    "Windows names": ["core-service/app/services/windows_names.py", "capsule-runner/app/shared/windows_names.py"],
    "secret files": ["core-service/app/secret_files.py", "auth-service/app/secret_files.py", "capsule-runner/app/secret_files.py"],
}


@pytest.mark.parametrize("name", sorted(COPIES))
def test_the_copies_are_identical(name: str) -> None:
    paths = [REPO / path for path in COPIES[name]]
    if not all(path.exists() for path in paths):
        pytest.skip("the other services are not beside this one (container image): checked in the repository")
    first = paths[0].read_bytes()
    different = [str(path.relative_to(REPO)) for path in paths[1:] if path.read_bytes() != first]
    assert not different, f"{name}: {', '.join(different)} differ from {COPIES[name][0]}; change every copy together"
