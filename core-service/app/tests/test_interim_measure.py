from types import SimpleNamespace

from app.services import scans


class FakeDb:
    def __init__(self, root):
        self.root = root

    def get(self, model, ident):
        return self.root

    def execute(self, *args, **kwargs):
        return None

    def commit(self):
        pass


def test_an_interim_measure_never_enters_the_history():
    root = SimpleNamespace(discovered_permissions_json={"content_stats": {"files": 10, "bytes": 100}, "content_size_bytes": 100, "content_previous": []})
    db = FakeDb(root)
    scans.record_module_state(db, 45, status="running", stats={"files": 12, "bytes": 120}, interim=True)
    shown = root.discovered_permissions_json
    assert shown["content_stats"]["files"] == 12 and shown["content_interim"] is True
    assert [p["stats"]["files"] for p in shown["content_previous"]] == [10]
    scans.record_module_state(db, 45, status="done", stats={"files": 12, "bytes": 125, "duplicates": {"groups": 3}})
    final = root.discovered_permissions_json
    assert final["content_stats"]["duplicates"]["groups"] == 3 and final["content_interim"] is False
    # Only the measure shown before the interim one is kept: the interim figures did not become a previous measure
    assert [p["stats"]["files"] for p in final["content_previous"]] == [10]


def test_running_without_interim_leaves_the_content():
    root = SimpleNamespace(discovered_permissions_json={"content_stats": {"files": 10, "bytes": 100}})
    scans.record_module_state(FakeDb(root), 45, status="running", stats={"files": 99, "bytes": 1}, progress={"chunks_done": 1})
    assert root.discovered_permissions_json["content_stats"]["files"] == 10
