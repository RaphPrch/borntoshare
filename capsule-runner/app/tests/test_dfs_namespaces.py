from __future__ import annotations

from app.actions import dfs_namespaces as action

TREE = {
    r"\\s\brest": [("Corporate", True, False), ("readme.txt", False, False)],
    r"\\s\brest\Corporate": [("Commons", True, False), ("Finance", True, True)],
    r"\\s\brest\Corporate\Commons": [("PiloteB2S", True, True)],
}


def test_dfs_folders_are_the_reparse_points_under_ordinary_folders():
    links = action.walk_links(r"\\s\brest", lambda path: TREE.get(path, []), max_links=100)
    assert links == ["Corporate\\Finance", "Corporate\\Commons\\PiloteB2S"]


def test_the_walk_stops_at_the_limit():
    assert action.walk_links(r"\\s\brest", lambda path: TREE.get(path, []), max_links=1) == ["Corporate\\Finance"]


def test_only_real_shares_can_be_namespaces():
    listing = "Disk|ADMIN$|x\nDisk|C$|x\nDisk|brest|\nDisk|SYSVOL|\nIPC|IPC$|\nDisk|lorient|"
    assert action.disk_shares(listing) == ["brest", "lorient"]


def test_a_namespace_path_names_its_server_and_namespace():
    assert action.namespace_from_path(r"\\corp.local\brest") == ("corp.local", "brest")
    assert action.namespace_from_path(r"\\DFS01\lorient\x") == ("DFS01", "lorient")
    assert action.namespace_from_path("DFS01") is None


def test_targets_keep_the_unc_form():
    assert action._clean_target(r"\FILER01\PiloteB2S") == r"\\FILER01\PiloteB2S"
