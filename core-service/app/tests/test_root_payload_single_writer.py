"""Only services/root_payload.py assigns storage_roots.discovered_permissions_json: every other writer merges its own
keys through merge_root_payload (a writer that rebuilt the dict erased the measures of 21 folders)."""
from __future__ import annotations

import re
from pathlib import Path

from app.services.root_payload import merge_root_payload

APP = Path(__file__).resolve().parents[1]
ASSIGN = re.compile(r"\.discovered_permissions_json\s*(?:\[[^\]]*\]\s*)?=(?!=)|setattr\([^)]*[\"']discovered_permissions_json[\"']")


def test_no_other_writer():
    offenders = []
    for path in APP.rglob("*.py"):
        if "tests" in path.parts or path.name == "root_payload.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ASSIGN.search(line) and not line.lstrip().startswith("#"):
                offenders.append(f"{path.relative_to(APP)}:{number}: {line.strip()}")
    assert not offenders, "use merge_root_payload:\n" + "\n".join(offenders)


def test_merge_keeps_what_others_wrote():
    class Root:
        discovered_permissions_json = {"content_stats": {"files": 3}, "permissions": [1]}

    root = Root()
    before = root.discovered_permissions_json
    merged = merge_root_payload(root, {"permissions": [], "probe_error": "x"})
    assert merged == {"content_stats": {"files": 3}, "permissions": [], "probe_error": "x"}
    assert root.discovered_permissions_json is not before  # a new dict: the JSON column is seen as changed
