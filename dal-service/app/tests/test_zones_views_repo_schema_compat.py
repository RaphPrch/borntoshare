from __future__ import annotations

from app.repositories.zones_views_repo import ZonesViewsRepo


class _FakeDB:
    pass


def _normalized_sql(sql: str) -> str:
    return " ".join(str(sql).split()).lower()


def test_list_reads_directly_from_v_zones(monkeypatch) -> None:
    repo = ZonesViewsRepo(_FakeDB())
    captured: dict[str, str] = {}

    def _capture(sql: str, params=None):  # noqa: ANN001, ANN202
        captured["sql"] = sql
        return []

    monkeypatch.setattr(repo, "_all_dicts", _capture)

    repo.list()

    sql = _normalized_sql(captured["sql"])
    assert "from v_zones v" in sql
    assert "left join zones" not in sql


def test_get_reads_directly_from_v_zones(monkeypatch) -> None:
    repo = ZonesViewsRepo(_FakeDB())
    captured: dict[str, str] = {}

    def _capture(sql: str, params=None):  # noqa: ANN001, ANN202
        captured["sql"] = sql
        return {"id": 1}

    monkeypatch.setattr(repo, "_one_dict", _capture)
    monkeypatch.setattr(repo, "list_console_endpoints", lambda _zone_id: [])

    repo.get(1)

    sql = _normalized_sql(captured["sql"])
    assert "from v_zones v" in sql
    assert "left join zones" not in sql
    assert "where v.id = :id" in sql


def test_list_console_endpoints_exposes_auth_aliases_for_zone_console(monkeypatch) -> None:
    repo = ZonesViewsRepo(_FakeDB())
    captured: dict[str, str] = {}

    def _capture(sql: str, params=None):  # noqa: ANN001, ANN202
        captured["sql"] = sql
        return []

    monkeypatch.setattr(repo, "_all_dicts", _capture)

    repo.list_console_endpoints(1101)

    sql = _normalized_sql(captured["sql"])
    assert "from v_zone_console_endpoints" in sql
    assert "bind_dn" in sql
    assert "bind_password_ref" in sql
    assert "bind_dn as auth_username" in sql
