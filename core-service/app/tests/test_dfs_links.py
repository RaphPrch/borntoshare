from __future__ import annotations

from types import SimpleNamespace

from app.services import dfs_links


class _Servers:
    def __init__(self, rows):
        self.rows = rows

    def match(self, server):
        return next((row for row in self.rows if row["alias"] == server.lower()), None)


SERVERS = _Servers([
    {"id": 1, "name": "FILER01", "host": "172.20.12.195", "alias": "filer01"},
    {"id": 2, "name": "FILER02", "host": "172.20.12.196", "alias": "filer02"},
])


def _namespace(links):
    return SimpleNamespace(capabilities={"dfs_snapshot": {"path": r"\\corp.local\brest", "links": links}})


def test_states_of_dfs_folders():
    links = [
        {"path": r"Commons\PiloteB2S", "targets": [r"\\FILER01\PiloteB2S"]},
        {"path": r"Corporate\RH", "targets": [r"\\FILER01\RH", r"\\FILER02\RH"]},
        {"path": r"Archives", "targets": [r"\\NAS-ARCH\Archives"]},
        {"path": r"Vide", "targets": []},
    ]
    roots = {(1, r"\\172.20.12.195\piloteb2s"): 10, (1, r"\\172.20.12.195\rh"): 11}
    out = dfs_links.describe_links(None, _namespace(links), servers=SERVERS, roots=roots)
    assert [link["state"] for link in out] == ["managed", "partial", "unknown_server", "no_target"]
    assert out[0]["dfs_path"] == r"\\corp.local\brest\Commons\PiloteB2S"
    assert out[0]["targets"][0]["root_path"] == r"\\172.20.12.195\PiloteB2S"
    assert out[1]["targets"][1]["storage_root_id"] is None


def test_unc_is_split_into_server_and_rest():
    assert dfs_links.split_unc(r"\\FILER01\Share\Dir") == ("FILER01", r"Share\Dir")
    assert dfs_links._norm(r"\\Host\Share\\Dir\\") == r"\\host\share\dir"
