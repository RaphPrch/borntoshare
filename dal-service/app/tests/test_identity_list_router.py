from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.routers import identity_list as router


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, executions):
        self._executions = list(executions)
        self.calls: list[str] = []

    def execute(self, stmt, _params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append(sql)
        if self._executions:
            rows = self._executions.pop(0)
        else:
            rows = []
        return _FakeResult(rows)

    def get(self, _model, _id):
        return None


class _UpdateDB:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self.commit_calls = 0
        self.user_display_name = "Alice"
        self.user_is_active = 1
        self.user_is_admin = 0
        self.group_display_name = "Finance Team"

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append((sql, dict(params or {})))

        normalized = " ".join(sql.split())
        if normalized.startswith("UPDATE identities SET"):
            if isinstance(params, dict):
                if "display_name" in params:
                    self.user_display_name = params["display_name"]
                if "is_active" in params:
                    self.user_is_active = params["is_active"]
                if "is_admin" in params:
                    self.user_is_admin = params["is_admin"]
            return _FakeResult([])
        if normalized.startswith("UPDATE directory_groups SET"):
            if isinstance(params, dict) and "display_name" in params:
                self.group_display_name = params["display_name"]
            return _FakeResult([])
        if "FROM identities WHERE id = :id LIMIT 1" in normalized and "SELECT id, username, display_name, is_active, type, auth_source" in normalized:
            return _FakeResult([{
                "id": 10,
                "username": "alice",
                "display_name": self.user_display_name,
                "is_active": self.user_is_active,
                "type": "user",
                "auth_source": "local",
            }])
        if "FROM identities WHERE id = :id LIMIT 1" in normalized and "SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type" in normalized:
            return _FakeResult([{
                "id": 10,
                "username": "alice",
                "display_name": self.user_display_name,
                "email": "alice@example.org",
                "auth_source": "local",
                "external_id": "alice",
                "source_id": None,
                "is_active": self.user_is_active,
                "type": "user",
            }])
        if "SELECT id FROM roles WHERE code = :code LIMIT 1" in normalized:
            code = str((params or {}).get("code") or "")
            if code == "platform_admin":
                return _FakeResult([{"id": 2}])
            if code == "user":
                return _FakeResult([{"id": 1}])
            return _FakeResult([])
        if "FROM directory_groups dg WHERE id = :id LIMIT 1" in normalized and "NULL AS is_active" in normalized:
            return _FakeResult([{
                "id": 31,
                "display_name": self.group_display_name,
                "username": None,
                "is_active": None,
                "type": "group",
                "auth_source": "ad",
            }])
        if "FROM directory_groups dg WHERE id = :id LIMIT 1" in normalized and "'group' AS type" in normalized:
            return _FakeResult([{
                "id": 31,
                "type": "group",
                "username": self.group_display_name,
                "display_name": self.group_display_name,
                "email": None,
                "auth_source": "ad",
                "external_id": "CN=Finance,OU=Groups,DC=corp,DC=local",
                "source_id": 5,
                "is_active": None,
            }])
        return _FakeResult([])

    def commit(self):
        self.commit_calls += 1


class _CreateDB:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self.commit_calls = 0

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append((sql, dict(params or {})))
        normalized = " ".join(sql.split())

        if "FROM identity_sources WHERE LOWER(COALESCE(type, '')) IN ('local', 'internal')" in normalized:
            return _FakeResult([{"id": 1}])
        if "FROM identities WHERE LOWER(COALESCE(username, '')) = LOWER(:username)" in normalized:
            return _FakeResult([])
        if "SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type FROM identities WHERE source_id = :source_id AND external_id = :external_id LIMIT 1" in normalized:
            external_id = str((params or {}).get("external_id") or "")
            source_id = int((params or {}).get("source_id") or 1)
            auth_source = "local" if external_id == "jdoe" else "ad"
            return _FakeResult([{
                "id": 51 if auth_source == "local" else 61,
                "username": external_id,
                "display_name": "John Doe" if auth_source == "local" else "John Directory",
                "email": "john@example.com",
                "auth_source": auth_source,
                "external_id": external_id,
                "source_id": source_id,
                "is_active": 1,
                "type": "user",
            }])
        if "SELECT id FROM roles WHERE code = :code LIMIT 1" in normalized:
            code = str((params or {}).get("code") or "")
            return _FakeResult([{"id": 2 if code == "platform_admin" else 1}])
        if "SELECT id, name, external_id, identity_source_id FROM directory_groups WHERE identity_source_id = :source_id AND external_id = :external_id AND deleted_at IS NULL LIMIT 1" in normalized:
            if str((params or {}).get("external_id") or "") == "CN=Platform Admins,OU=Groups,DC=corp,DC=local":
                return _FakeResult([{
                    "id": 71,
                    "name": "Platform Admins",
                    "external_id": "CN=Platform Admins,OU=Groups,DC=corp,DC=local",
                    "identity_source_id": int((params or {}).get("source_id") or 5),
                }])
            return _FakeResult([])
        if "SELECT dg.id, 'group' AS type, dg.name AS username, dg.name AS display_name, NULL AS email, 'ad' AS auth_source, dg.external_id, dg.identity_source_id AS source_id, NULL AS is_active FROM directory_groups dg WHERE id = :id LIMIT 1" in normalized:
            return _FakeResult([{
                "id": 71,
                "type": "group",
                "username": "Platform Admins",
                "display_name": "Platform Admins",
                "email": None,
                "auth_source": "ad",
                "external_id": "CN=Platform Admins,OU=Groups,DC=corp,DC=local",
                "source_id": 5,
                "is_active": None,
            }])
        return _FakeResult([])

    def get(self, model, pk):
        if getattr(model, "__name__", "") == "IdentitySource" and int(pk) == 5:
            return type("IdentitySource", (), {"id": 5, "type": "ad", "is_active": True})()
        return None

    def commit(self):
        self.commit_calls += 1


class _DeleteDB:
    def __init__(self, *, user_row=None, group_row=None) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self.commit_calls = 0
        self.user_row = user_row
        self.group_row = group_row

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append((sql, dict(params or {})))
        normalized = " ".join(sql.split())

        if "FROM identities i WHERE i.id = :id LIMIT 1" in normalized:
            return _FakeResult([self.user_row] if self.user_row else [])
        if "FROM directory_groups dg WHERE dg.id = :id" in normalized:
            return _FakeResult([self.group_row] if self.group_row else [])
        return _FakeResult([])

    def commit(self):
        self.commit_calls += 1


def test_list_identity_overview_admin_login_scope_returns_local_users_only() -> None:
    db = _FakeDB(
        executions=[
            [
                {
                    "id": 11,
                    "type": "user",
                    "username": "admin.local",
                    "display_name": "Admin Local",
                    "email": "admin.local@example.com",
                    "auth_source": "local",
                    "external_id": "admin.local",
                    "source_id": 2,
                    "snapshot_source": None,
                    "provisioning_source": "system",
                    "is_active": 1,
                }
            ]
        ]
    )

    out = router.list_identity_overview(scope="admin_login", db=db)
    data = out.get("data") if isinstance(out, dict) else {}
    meta = out.get("meta") if isinstance(out, dict) else {}

    users = data.get("users") if isinstance(data, dict) else []
    groups = data.get("groups") if isinstance(data, dict) else []
    items = data.get("items") if isinstance(data, dict) else []

    assert len(db.calls) == 2
    assert "FROM directory_groups" not in db.calls[0]
    assert "LOWER(COALESCE(i.auth_source, '')) = 'local'" in db.calls[0]
    assert "FROM v_identity_effective_roles" in db.calls[1]

    assert isinstance(users, list)
    assert isinstance(groups, list)
    assert isinstance(items, list)
    assert len(users) == 1
    assert len(groups) == 0
    assert len(items) == 1
    assert users[0]["auth_source"] == "local"
    assert users[0]["snapshot_source"] is None

    assert meta.get("users_count") == 1
    assert meta.get("groups_count") == 0
    assert meta.get("count") == 1


def test_list_identity_overview_default_scope_excludes_directory_groups_and_snapshot_auto_imports() -> None:
    db = _FakeDB(
        executions=[
            [
                {
                    "id": 21,
                    "type": "user",
                    "username": "admin.local",
                    "display_name": "Admin Local",
                    "email": "admin.local@example.com",
                    "auth_source": "local",
                    "external_id": "admin.local",
                    "source_id": None,
                    "snapshot_source": None,
                    "provisioning_source": "system",
                    "is_active": 1,
                }
            ],
            [],
            [
                {"identity_id": 21, "role_code": "user"}
            ],
        ]
    )

    out = router.list_identity_overview(scope=None, db=db)
    data = out.get("data") if isinstance(out, dict) else {}
    meta = out.get("meta") if isinstance(out, dict) else {}

    users = data.get("users") if isinstance(data, dict) else []
    groups = data.get("groups") if isinstance(data, dict) else []
    items = data.get("items") if isinstance(data, dict) else []

    assert len(db.calls) == 3
    assert "FROM identities" in db.calls[0]
    assert "FROM directory_groups" in db.calls[1]
    assert "legacy_auto_snapshot" in db.calls[0]
    assert "FROM v_identity_effective_roles" in db.calls[2]

    assert len(users) == 1
    assert len(groups) == 0
    assert len(items) == 1
    assert users[0]["auth_source"] == "local"
    assert users[0]["provisioning_source"] == "system"

    assert meta.get("users_count") == 1
    assert meta.get("groups_count") == 0
    assert meta.get("count") == 1


def test_list_identity_overview_default_scope_includes_explicit_directory_groups() -> None:
    db = _FakeDB(
        executions=[
            [],
            [
                {
                    "id": 31,
                    "external_id": "CN=Finance,OU=Groups,DC=corp,DC=local",
                    "dn": "CN=Finance,OU=Groups,DC=corp,DC=local",
                    "identity_source_id": 5,
                    "display_name": "Finance Team",
                    "created_at": None,
                    "updated_at": None,
                    "last_snapshot_at": None,
                    "source_name": "Active Directory - Corp",
                    "members_count": 12,
                }
            ],
            [
                {"directory_group_id": 31, "role_code": "platform_admin"}
            ],
        ]
    )

    out = router.list_identity_overview(scope=None, db=db)
    data = out.get("data") if isinstance(out, dict) else {}
    groups = data.get("groups") if isinstance(data, dict) else []

    assert len(groups) == 1
    assert groups[0]["id"] == 31
    assert groups[0]["display_name"] == "Finance Team"
    assert groups[0]["roles"] == ["platform_admin"]
    assert groups[0]["members_count"] == 12


def test_update_identity_user_supports_application_role_and_active_flag(monkeypatch) -> None:
    db = _UpdateDB()
    logged: list[dict] = []

    monkeypatch.setattr(router, "log_activity", lambda *_a, **kwargs: logged.append(kwargs))

    request = type("Req", (), {"headers": {}})()
    out = __import__("asyncio").run(
        router.update_identity(
            10,
            request=request,
            payload={
                "identity_type": "user",
                "display_name": "Alice Updated",
                "is_active": False,
                "application_role": "platform_admin",
            },
            db=db,
        )
    )

    data = out.get("data") if isinstance(out, dict) else {}
    assert data["application_role"] == "platform_admin"
    assert data["is_active"] is False
    assert db.commit_calls == 1
    assert any("UPDATE identities" in sql and "status = :status" in sql for sql, _ in db.calls)
    assert any("DELETE ir" in sql and "FROM identity_roles ir" in sql for sql, _ in db.calls)
    assert any("INSERT INTO identity_roles" in sql for sql, _ in db.calls)
    assert any(entry.get("action") == "identity.application_role_updated" for entry in logged)


def test_update_identity_group_updates_directory_group_and_role(monkeypatch) -> None:
    db = _UpdateDB()
    logged: list[dict] = []

    monkeypatch.setattr(router, "log_activity", lambda *_a, **kwargs: logged.append(kwargs))

    request = type("Req", (), {"headers": {}})()
    out = __import__("asyncio").run(
        router.update_identity(
            31,
            request=request,
            payload={
                "identity_type": "group",
                "display_name": "Finance Team Updated",
                "application_role": "user",
            },
            db=db,
        )
    )

    data = out.get("data") if isinstance(out, dict) else {}
    assert data["type"] == "group"
    assert data["application_role"] == "user"
    assert db.commit_calls == 1
    assert any("UPDATE directory_groups" in sql for sql, _ in db.calls)
    assert any("INSERT INTO identity_roles" in sql and call_params.get("directory_group_id") == 31 for sql, call_params in db.calls)
    assert any(entry.get("target_type") == "identity_group" for entry in logged)


def test_create_identity_local_user_creates_credentials_and_role(monkeypatch) -> None:
    db = _CreateDB()
    logged: list[dict] = []

    monkeypatch.setattr(router, "log_activity", lambda *_a, **kwargs: logged.append(kwargs))
    monkeypatch.setattr(router, "_hash_b2s_password", lambda password: f"hashed::{password}")

    request = type("Req", (), {"headers": {}})()
    out = __import__("asyncio").run(
        router.create_identity(
            request=request,
            payload={
                "identity_type": "user",
                "auth_source": "local",
                "username": "jdoe",
                "display_name": "John Doe",
                "email": "john@example.com",
                "temporary_password": "Secret123!",
                "application_role": "user",
            },
            db=db,
        )
    )

    data = out.get("data") if isinstance(out, dict) else {}
    assert data["id"] == 51
    assert data["auth_source"] == "local"
    assert data["application_role"] == "user"
    assert db.commit_calls == 1
    assert any("INSERT INTO identities" in sql for sql, _ in db.calls)
    assert any("INSERT INTO local_credentials" in sql and call_params.get("password_hash") == "hashed::Secret123!" for sql, call_params in db.calls)
    assert any("INSERT INTO identity_roles" in sql for sql, _ in db.calls)
    assert any(entry.get("action") == "identity.account_created" for entry in logged)


def test_create_identity_directory_group_assigns_role(monkeypatch) -> None:
    db = _CreateDB()
    logged: list[dict] = []

    monkeypatch.setattr(router, "log_activity", lambda *_a, **kwargs: logged.append(kwargs))

    request = type("Req", (), {"headers": {}})()
    out = __import__("asyncio").run(
        router.create_identity(
            request=request,
            payload={
                "identity_type": "group",
                "auth_source": "ad",
                "identity_source_id": 5,
                "application_role": "platform_admin",
                "principal": {
                    "type": "group",
                    "external_id": "CN=Platform Admins,OU=Groups,DC=corp,DC=local",
                    "dn": "CN=Platform Admins,OU=Groups,DC=corp,DC=local",
                    "display_name": "Platform Admins",
                },
            },
            db=db,
        )
    )

    data = out.get("data") if isinstance(out, dict) else {}
    assert data["id"] == 71
    assert data["type"] == "group"
    assert data["application_role"] == "platform_admin"
    assert db.commit_calls == 1
    assert any("UPDATE directory_groups" in sql for sql, _ in db.calls)
    assert any("INSERT INTO identity_roles" in sql and call_params.get("directory_group_id") == 71 for sql, call_params in db.calls)
    assert any(entry.get("action") == "identity.group_access_granted" for entry in logged)


def test_delete_identity_rejects_default_local_admin(monkeypatch) -> None:
    db = _DeleteDB(
        user_row={
            "id": 10,
            "username": "admin",
            "display_name": "admin",
            "auth_source": "local",
            "provisioning_source": "system",
            "type": "user",
        }
    )

    request = type("Req", (), {"headers": {}})()
    try:
        __import__("asyncio").run(
            router.delete_identity(
                10,
                request=request,
                identity_type="user",
                db=db,
            )
        )
        assert False, "expected HTTPException"
    except Exception as exc:
        from fastapi import HTTPException

        assert isinstance(exc, HTTPException)
        assert exc.status_code == 403
        assert "cannot be deleted" in str(exc.detail).lower()

    assert db.commit_calls == 0
    assert not any("DELETE FROM identities" in sql for sql, _ in db.calls)


def test_delete_identity_group_removes_application_access_only(monkeypatch) -> None:
    db = _DeleteDB(
        group_row={
            "id": 31,
            "display_name": "Finance Team",
            "external_id": "CN=Finance,OU=Groups,DC=corp,DC=local",
            "source_id": 5,
            "auth_source": "ad",
            "type": "group",
        }
    )
    logged: list[dict] = []

    monkeypatch.setattr(router, "log_activity", lambda *_a, **kwargs: logged.append(kwargs))

    request = type("Req", (), {"headers": {}})()
    out = __import__("asyncio").run(
        router.delete_identity(
            31,
            request=request,
            identity_type="group",
            db=db,
        )
    )

    data = out.get("data") if isinstance(out, dict) else {}
    assert data["deleted"] is True
    assert data["type"] == "group"
    assert db.commit_calls == 1
    assert any("DELETE FROM identity_roles" in sql for sql, _ in db.calls)
    assert not any("DELETE FROM identities" in sql for sql, _ in db.calls)
    assert any(entry.get("action") == "identity.group_access_revoked" for entry in logged)
