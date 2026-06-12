import pytest
from fastapi import HTTPException

from app.routers.storage_roots import (
    _is_child_root_path,
    _normalize_storage_root_path,
    _validate_child_storage_roots_remain_nested,
)


class _RowsResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> "_RowsResult":
        return self

    def all(self) -> list[dict[str, object]]:
        return self.rows


class _ChildRowsSession:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def execute(self, *_args: object, **_kwargs: object) -> _RowsResult:
        return _RowsResult(self.rows)


def test_normalize_storage_root_path_handles_windows_paths() -> None:
    assert _normalize_storage_root_path(r"C:\Share1\Share2\\") == "c:/share1/share2"


def test_child_path_detection_requires_nested_path() -> None:
    assert _is_child_root_path(child=r"C:\share1\share2", parent=r"C:\share1")
    assert not _is_child_root_path(child=r"C:\share10", parent=r"C:\share1")
    assert not _is_child_root_path(child=r"C:\share1", parent=r"C:\share1")


def test_child_roots_remain_nested_accepts_valid_children() -> None:
    session = _ChildRowsSession([
        {"id": 2, "name": "Share 2", "root_path": r"C:\share1\share2", "storage_endpoint_id": 10}
    ])

    _validate_child_storage_roots_remain_nested(
        session,  # type: ignore[arg-type]
        parent_storage_root_id=1,
        storage_endpoint_id=10,
        root_path=r"C:\share1",
    )


def test_child_roots_remain_nested_rejects_endpoint_move() -> None:
    session = _ChildRowsSession([
        {"id": 2, "name": "Share 2", "root_path": r"C:\share1\share2", "storage_endpoint_id": 10}
    ])

    with pytest.raises(HTTPException) as exc:
        _validate_child_storage_roots_remain_nested(
            session,  # type: ignore[arg-type]
            parent_storage_root_id=1,
            storage_endpoint_id=11,
            root_path=r"C:\share1",
        )

    assert exc.value.status_code == 422


def test_child_roots_remain_nested_rejects_path_move() -> None:
    session = _ChildRowsSession([
        {"id": 2, "name": "Share 2", "root_path": r"C:\share1\share2", "storage_endpoint_id": 10}
    ])

    with pytest.raises(HTTPException) as exc:
        _validate_child_storage_roots_remain_nested(
            session,  # type: ignore[arg-type]
            parent_storage_root_id=1,
            storage_endpoint_id=10,
            root_path=r"C:\archive",
        )

    assert exc.value.status_code == 422
