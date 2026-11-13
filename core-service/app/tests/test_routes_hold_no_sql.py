"""Routes do not talk to the database: SQL and ORM calls live in app/data (repositories) and app/services.

The routes written before this rule are listed with what they still hold: the number may only go down (a route moved
to a service leaves the list). A new route file holds none. Counted: text( … ) and db.query / get / add / delete / execute.
"""
from __future__ import annotations

import re
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "api"
SQL = re.compile(r"\btext\(|\bdb\.(?:query|get|add|delete|execute)\(")

# Left to move (2026-11-13): file -> SQL calls it still holds
REMAINING = {'identity_list.py': 8, 'identity_sources.py': 19, 'infrastructure.py': 4, 'observability.py': 1, 'provisioning_internal.py': 10, 'storage_endpoints.py': 18, 'storage_roots.py': 30, 'tags.py': 12, 'zones.py': 2}


def _count(path: Path) -> int:
    return len(SQL.findall(path.read_text(encoding="utf-8")))


def test_routes_hold_no_new_sql():
    grown = []
    for path in sorted(API.glob("*.py")):
        found, allowed = _count(path), REMAINING.get(path.name, 0)
        if found > allowed:
            grown.append(f"{path.name}: {found} SQL call(s), {allowed} allowed — move them to app/services or app/data")
    assert not grown, "\n".join(grown)


def test_the_list_follows_the_moves():
    """A file that holds less than listed: lower its number here (the list only shrinks)."""
    stale = [f"{name}: listed {allowed}, holds {_count(API / name)}" for name, allowed in REMAINING.items()
             if (API / name).exists() and _count(API / name) < allowed]
    assert not stale, "\n".join(stale)
