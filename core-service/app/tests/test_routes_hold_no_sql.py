"""Routes do not talk to the database: every SQL statement lives in app/data (repositories) or app/services.

- Written SQL (text( … ), db.execute, db.query): none at all in a route file.
- Loading or saving one ORM object by id (db.get / db.add / db.delete, the unit of work of the session): allowed where
  it is today, never more (the count of a file may only go down).
"""
from __future__ import annotations

import re
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "api"
SQL = re.compile(r"\btext\(|\bdb\.(?:query|execute)\(")
ORM = re.compile(r"\bdb\.(?:get|add|delete)\(")

# ORM object calls left in the routes (2026-11-13): file -> count
ORM_CALLS = {'identity_list.py': 2, 'identity_sources.py': 4, 'provisioning_internal.py': 4, 'storage_endpoints.py': 15, 'storage_roots.py': 28, 'tags.py': 8}


def test_routes_hold_no_sql():
    found = [f"{path.name}: {len(SQL.findall(path.read_text(encoding='utf-8')))} statement(s)" for path in sorted(API.glob("*.py"))
             if SQL.search(path.read_text(encoding="utf-8"))]
    assert not found, "move them to app/data/repositories or app/services:\n" + "\n".join(found)


def test_orm_calls_do_not_grow():
    grown = []
    for path in sorted(API.glob("*.py")):
        count, allowed = len(ORM.findall(path.read_text(encoding="utf-8"))), ORM_CALLS.get(path.name, 0)
        if count > allowed:
            grown.append(f"{path.name}: {count} ORM calls, {allowed} allowed")
    assert not grown, "\n".join(grown)
