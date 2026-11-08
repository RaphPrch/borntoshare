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


def test_folders_below_a_dfs_target_get_their_dfs_path(monkeypatch):
    rows = [
        {"id": 10, "storage_endpoint_id": 1, "root_path": r"\\172.20.12.195\PiloteB2S"},
        {"id": 12, "storage_endpoint_id": 1, "root_path": r"\\172.20.12.195\PiloteB2S\Finance\2026"},
        {"id": 13, "storage_endpoint_id": 1, "root_path": r"\\172.20.12.195\PiloteB2Sv2\Finance"},
    ]

    class _Result:
        def mappings(self):
            return self

        def all(self):
            return rows

    class _Db:
        def query(self, _model):
            return SimpleNamespace(filter=lambda *_a: SimpleNamespace(all=lambda: [_namespace([{"path": r"Commons\Pilote", "targets": [r"\\FILER01\PiloteB2S"]}])]))

        def execute(self, *_a, **_k):
            return _Result()

    monkeypatch.setattr(dfs_links, "_Servers", lambda _db: SERVERS)
    paths, replicas = dfs_links._compute(_Db())
    assert paths[10] == r"\\corp.local\brest\Commons\Pilote"
    assert paths[12] == r"\\corp.local\brest\Commons\Pilote\Finance\2026"
    assert 13 not in paths
    assert replicas == {10: []}
