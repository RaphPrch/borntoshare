from __future__ import annotations

import os

# Governance settings require a Dramatiq broker URL; the broker never connects in tests.
os.environ.setdefault("CAPSULE_BROKER_URL", "redis://localhost:6379/15")
