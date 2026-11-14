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


def test_the_domain_of_a_namespace_comes_from_its_path():
    assert action.domain_of_path(r"\\corp.local\brest", "DFS01.CORP.LOCAL") == "corp.local"
    assert action.domain_of_path(r"\\DFS01\lorient", "DFS01.CORP.LOCAL") == ""
    assert action.domain_of_path(r"\\dfs01.corp.local\lorient", "DFS01") == ""
    assert action.domain_of_path("", "DFS01") == ""


def test_a_dfs_folder_without_target_is_not_a_link():
    """\\\\corp.local\\Grenoble: Corporate\\TEST is a DFS folder without target, marked by a hidden « .DFSFolderLink »
    reparse point whose referral is empty (it made the whole namespace « not read: list index out of range »)."""
    tree = {
        r"\\s\Grenoble": [("Corporate", True, False)],
        r"\\s\Grenoble\Corporate": [("Direction", True, True), ("TEST", True, False)],
        r"\\s\Grenoble\Corporate\TEST": [(".DFSFolderLink", True, True), ("Sub", True, True)],
    }
    links = action.walk_links(r"\\s\Grenoble", lambda path: tree.get(path, []), max_links=100)
    assert links == ["Corporate\\Direction", "Corporate\\TEST\\Sub"]
