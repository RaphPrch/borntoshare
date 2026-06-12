from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.access_requests_views_repo import (
    AccessRequestsReadModelContractError,
    AccessRequestsViewsRepo,
)


class _FailingExecuteDB:
    def __init__(self, *, fail_on: str):
        self.fail_on = str(fail_on).lower()

    def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(statement).lower()
        if self.fail_on in sql:
            raise SQLAlchemyError(f"missing view for {self.fail_on}")

        if "from v_access_requests" in sql and "where request_id" in sql:
            row = {
                "request_id": 123,
                "request_code": "AR-123",
                "status": "pending",
                "created_at": None,
                "updated_at": None,
                "scope_type": "storage_root",
                "scope_display": "/storage_root/1",
                "target_path": "/srv/data",
                "storage_root_id": 1,
                "storage_root_name": "Root 1",
                "access_profile_name": "READ",
            }
            return SimpleNamespace(
                mappings=lambda: SimpleNamespace(first=lambda: row, all=lambda: [row])
            )

        return SimpleNamespace(
            mappings=lambda: SimpleNamespace(first=lambda: None, all=lambda: [])
        )


@pytest.mark.parametrize(
    "view_name, expected_code_fragment",
    [
        ("from v_access_requests", "v_access_requests"),
        ("from v_access_request_timeline", "v_access_request_timeline"),
        ("from v_access_request_provisioning", "v_access_request_provisioning"),
    ],
)
def test_get_details_raises_contract_error_when_required_view_missing(
    view_name: str,
    expected_code_fragment: str,
) -> None:
    repo = AccessRequestsViewsRepo(_FailingExecuteDB(fail_on=view_name))

    with pytest.raises(AccessRequestsReadModelContractError) as exc:
        repo.get_details(123)

    message = str(exc.value)
    assert "read-model contract violation" in message.lower()
    assert expected_code_fragment in message
