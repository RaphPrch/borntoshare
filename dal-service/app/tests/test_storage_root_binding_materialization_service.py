from __future__ import annotations

from app.services import storage_root_binding_materialization_service as module


class _FakeResult:
    def __init__(self, rows: list[dict] | None = None):
        self._rows = list(rows or [])

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self):
        self.rows = {
            "root_context": [{"storage_root_id": 7, "root_path": r"\\files\corp\finance", "zone_id": 3}],
            "zone_candidates": [
                {
                    "access_profile_id": 11,
                    "profile_code": "READ",
                    "profile_name": "STD_READ",
                    "permission_candidate": "READ",
                },
                {
                    "access_profile_id": 12,
                    "profile_code": "WRITE",
                    "profile_name": "STD_WRITE",
                    "permission_candidate": "WRITE",
                },
            ],
            "explicit_candidates": [],
            "active_rows": [],
            "all_roots": [{"id": 7}],
            "roots_for_zone": [{"id": 7}],
        }
        self.exec_log: list[tuple[str, dict]] = []
        self.commit_calls = 0

    def execute(self, statement, params=None):
        sql = str(statement)
        low = sql.lower()
        payload = dict(params or {})
        self.exec_log.append((sql, payload))

        if (
            "from storage_roots sr" in low
            and "join storage_endpoints se on se.id = sr.storage_endpoint_id" in low
            and "where sr.id = :storage_root_id" in low
            and "sr.root_path as root_path" in low
        ):
            return _FakeResult(self.rows.get("root_context", []))
        if "join zone_access_profiles zap" in low and "where sr.id = :storage_root_id" in low:
            return _FakeResult(self.rows.get("zone_candidates", []))
        if (
            "from storage_root_access_profiles srap" in low
            and "join access_profiles ap on ap.id = srap.access_profile_id" in low
            and "where srap.storage_root_id = :storage_root_id" in low
            and "nullif(srap.source" in low
        ):
            return _FakeResult(self.rows.get("explicit_candidates", []))
        if (
            "from storage_root_access_profiles srap" in low
            and "join access_profiles ap on ap.id = srap.access_profile_id" in low
            and "permission_candidate" in low
            and "order by" in low
            and "group_external_id" in low
        ):
            return _FakeResult(self.rows.get("active_rows", []))
        if low.strip().startswith("select id from storage_roots order by id asc"):
            return _FakeResult(self.rows.get("all_roots", []))
        if (
            "select sr.id" in low
            and "from storage_roots sr" in low
            and "join storage_endpoints se on se.id = sr.storage_endpoint_id" in low
            and "where se.zone_id = :zone_id" in low
        ):
            return _FakeResult(self.rows.get("roots_for_zone", []))
        return _FakeResult([])

    def commit(self):
        self.commit_calls += 1


def test_materialize_root_bindings_creates_read_and_write(monkeypatch) -> None:
    db = _FakeDB()
    monkeypatch.setattr(
        module,
        "resolve_group_name",
        lambda db, zone_ref, storage_root_path, perm, profile=None: {"samAccountName": f"B2S_{perm}"},
    )

    report = module.materialize_root_bindings(db, storage_root_id=7, replace_stale=True, commit=True)
    payload = report.to_dict()

    assert payload["created_rows"] == 2
    assert payload["approval_ready"] is True
    assert db.commit_calls == 1


def test_materialize_root_bindings_detects_ambiguous_candidates(monkeypatch) -> None:
    db = _FakeDB()
    db.rows["zone_candidates"] = [
        {"access_profile_id": 11, "profile_code": "READ", "profile_name": "A", "permission_candidate": "READ"},
        {"access_profile_id": 13, "profile_code": "READ", "profile_name": "B", "permission_candidate": "READ"},
    ]
    monkeypatch.setattr(
        module,
        "resolve_group_name",
        lambda db, zone_ref, storage_root_path, perm, profile=None: {"samAccountName": f"B2S_{perm}"},
    )

    report = module.materialize_root_bindings(db, storage_root_id=7, replace_stale=True, commit=False)
    payload = report.to_dict()

    assert any("ambiguous_read" == warning for warning in payload["ambiguity_warnings"])
    assert payload["approval_ready"] is False


def test_materialize_root_bindings_rewrites_legacy_group_name_with_expected_naming(monkeypatch) -> None:
    db = _FakeDB()
    db.rows["explicit_candidates"] = [
        {
            "id": 901,
            "storage_root_id": 7,
            "access_profile_id": 12,
            "source": "MANUAL",
            "profile_code": "WRITE",
            "profile_name": "STD_WRITE",
            "group_name": "SR7_WRITE",
            "group_external_id": None,
            "status": "QUEUED",
            "permission_candidate": "WRITE",
        }
    ]
    monkeypatch.setattr(
        module,
        "resolve_group_name",
        lambda db, zone_ref, storage_root_path, perm, profile=None: {"samAccountName": f"B2S_FINANCE_{perm}"},
    )

    report = module.materialize_root_bindings(db, storage_root_id=7, replace_stale=True, commit=False)
    payload = report.to_dict()

    assert payload["updated_rows"] >= 1
    assert payload["approval_ready"] is True

    updates = [
        (sql, params)
        for (sql, params) in db.exec_log
        if "UPDATE storage_root_access_profiles" in str(sql)
    ]
    assert any(str((params or {}).get("group_name") or "") == "B2S_FINANCE_WRITE" for (_sql, params) in updates)


def test_resync_roots_for_zone_returns_aggregate_report(monkeypatch) -> None:
    db = _FakeDB()
    monkeypatch.setattr(
        module,
        "resolve_group_name",
        lambda db, zone_ref, storage_root_path, perm, profile=None: {"samAccountName": f"B2S_{perm}"},
    )

    out = module.resync_roots_for_zone(db, zone_id=3, replace_stale=True, commit=True)
    assert int(out.get("zone_id") or 0) == 3
    assert int(out.get("roots_count") or 0) == 1
    assert int(out.get("created_rows") or 0) >= 1
    assert db.commit_calls == 1
