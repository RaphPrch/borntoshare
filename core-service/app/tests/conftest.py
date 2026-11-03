from __future__ import annotations

import os

# Every request to core-service carries the token shared by the services
os.environ.setdefault("INTERNAL_TOKEN", "tests-internal-token")
TEST_INTERNAL_HEADERS = {"X-Internal-Token": os.environ["INTERNAL_TOKEN"]}

# Governance settings require a Dramatiq broker URL; the broker never connects in tests.
os.environ.setdefault("CAPSULE_BROKER_URL", "redis://localhost:6379/15")
