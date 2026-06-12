from __future__ import annotations

from app.routers import zones as router


class _Result:
    def __init__(self, *, lastrowid: int = 0, scalar_value=None):
        self.lastrowid = lastrowid
        self._scalar_value = scalar_value

    def scalar(self):
        return self._scalar_value


class _FakeMappings:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _ExecuteReturn:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return _FakeMappings(self._row)


class _FakeDB:
    def __init__(self):
        self.statements: list[str] = []
        self.params: list[dict] = []

    def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(dict(params or {}))
        normalized = " ".join(sql.lower().split())

        if "insert into zones" in normalized:
            return _Result(lastrowid=77)
        if "select last_insert_id()" in normalized:
            return _Result(scalar_value=77)
        if "select count(1)" in normalized and "from storage_endpoints" in normalized:
            return _Result(scalar_value=0)
        if normalized.startswith("select") and "from zones" in normalized and "where id = :id" in normalized:
            return _ExecuteReturn(
                {
                    "id": int((params or {}).get("id") or 1),
                    "name": "Z1",
                    "code": "Z1",
                    "description": None,
                }
            )
        if normalized.startswith("delete from zones"):
            return _Result()
        if normalized.startswith("update zones set"):
            return _Result()
        return _Result()

    def commit(self):
        return None

    def rollback(self):
        return None


def _payload_create(**overrides):
    data = {
        "name": "Zone A",
        "code": "ZA",
        "description": None,
    }
    data.update(overrides)
    return router.ZoneCreate(**data)


def _payload_update(**overrides):
    return router.ZoneUpdate(**dict(overrides))


def test_create_zone_uses_canonical_zone_columns(monkeypatch) -> None:
    db = _FakeDB()
    monkeypatch.setattr(router, "log_activity", lambda *_args, **_kwargs: None)

    out = router.create_zone(_payload_create(), db)

    insert_sql = "\n".join(db.statements).lower()
    assert "insert into zones (name, code, description)" in insert_sql
    assert (out.get("data") or {}).get("id") == 77


def test_update_zone_only_updates_zone_identity_fields(monkeypatch) -> None:
    db = _FakeDB()
    monkeypatch.setattr(router, "log_activity", lambda *_args, **_kwargs: None)

    router.update_zone(5, _payload_update(name="Zone B", code="ZB"), db)

    updates = [s.lower() for s in db.statements if s.lower().startswith("update zones set")]
    assert len(updates) == 1
    assert "name = :name" in updates[0]
    assert "code = :code" in updates[0]


def test_get_zone_returns_canonical_zone_fields() -> None:
    db = _FakeDB()

    out = router.get_zone(5, db)

    data = out.get("data") or {}
    assert data["id"] == 5
    assert data["name"] == "Z1"
    assert set(data.keys()) == {"id", "name", "code", "description"}
