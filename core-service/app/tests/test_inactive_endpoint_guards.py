from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import storage_endpoints


class _Db:
    def __init__(self, endpoint):
        self.endpoint = endpoint

    def get(self, _model, _id):
        return self.endpoint


def _endpoint(**over):
    base = {"id": 1, "is_active": True, "status": "active", "host": "filer01", "bind_dn": "CORP\\b2s", "bind_password_ref": "sm://x"}
    return SimpleNamespace(**{**base, **over})


@pytest.mark.parametrize("over", [{"is_active": False}, {"status": "disabled"}])
def test_no_share_on_a_disabled_file_server(over) -> None:
    with pytest.raises(HTTPException) as caught:
        storage_endpoints._share_endpoint(_Db(_endpoint(**over)), 1)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "STORAGE_ENDPOINT_INACTIVE"


def test_an_active_file_server_takes_shares() -> None:
    endpoint = _endpoint()
    assert storage_endpoints._share_endpoint(_Db(endpoint), 1) is endpoint
