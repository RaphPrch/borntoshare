"""Access Explorer: the computation from ACL entries and the membership graph (no database: the inputs in memory)."""
from __future__ import annotations

from app.services.access_explorer import (
    LIMIT_DEPTH,
    account_state,
    ace_info,
    folders_from_entries,
    summarize,
    walk,
)
from app.services.root_payload import acl_index_rows


def _edges(graph: dict[str, list[str]]):
    """Upward graph: member → the groups holding it."""
    def edges(frontier):
        return [(group, member) for member in frontier for group in graph.get(member, [])]
    return edges


def test_nested_groups_keep_their_full_path() -> None:
    # paul ∈ GG_Compta ∈ GG_Finance_Write ∈ GL_Finance_All
    graph = {"paul": ["GG_Compta"], "GG_Compta": ["GG_Finance_Write"], "GG_Finance_Write": ["GL_Finance_All"]}
    nodes = walk(_edges(graph), "paul")["nodes"]
    assert nodes["GG_Compta"] == {"depth": 0, "path": ["GG_Compta"]}
    assert nodes["GG_Finance_Write"] == {"depth": 1, "path": ["GG_Compta", "GG_Finance_Write"]}
    assert nodes["GL_Finance_All"]["path"] == ["GG_Compta", "GG_Finance_Write", "GL_Finance_All"]


def test_group_loops_end_and_the_shortest_path_wins() -> None:
    # A ∈ B ∈ A (a loop), and paul in both A and C ∈ B: B is reached at depth 1 through either, never walked twice
    graph = {"paul": ["A", "C"], "A": ["B"], "B": ["A"], "C": ["B"]}
    result = walk(_edges(graph), "paul")
    assert set(result["nodes"]) == {"A", "B", "C"}
    assert result["nodes"]["B"]["depth"] == 1 and not result["truncated"]


def test_depth_is_limited() -> None:
    chain = {f"g{i}": [f"g{i + 1}"] for i in range(30)}
    result = walk(_edges({"paul": ["g0"], **chain}), "paul", max_depth=5)
    assert result["truncated"] and max(n["depth"] for n in result["nodes"].values()) == 5
    assert LIMIT_DEPTH == "group_depth_truncated"


def test_entries_direct_inherited_and_deny() -> None:
    explicit = ace_info("CORP\\GG_Finance_Write", "ALLOWED/OI|CI/RWXD")
    inherited = ace_info("CORP\\GG_Finance_Read", "ALLOWED/OI|CI|I/READ")
    denied = ace_info("CORP\\paul", "DENIED/OI|CI/RWXD")
    assert (explicit["rights"], explicit["inherited"], explicit["deny"]) == ("modify", False, False)
    assert (inherited["rights"], inherited["inherited"]) == ("read", True)
    # The denied right is read from the mask: « Modify denied », not just « denied »
    assert (denied["rights"], denied["deny"]) == ("modify", True)


def test_several_paths_and_a_deny_are_said() -> None:
    grants = [{**ace_info("CORP\\GG_A", "ALLOWED/OI|CI|I/READ"), "kind": "group"},
              {**ace_info("CORP\\GG_B", "ALLOWED/OI|CI/RWXD"), "kind": "nested"}]
    summary = summarize(grants)
    assert summary == {"ntfs_rights": "modify", "denied": False, "paths": 2, "multiple_paths": True, "inherited_only": False}
    with_deny = summarize([*grants, {**ace_info("CORP\\paul", "DENIED/0x0/READ"), "kind": "direct"}])
    assert with_deny["denied"] and with_deny["ntfs_rights"] == "modify"
    assert summarize([])["ntfs_rights"] is None


def test_folders_of_a_user_with_their_origins() -> None:
    origins = {
        "paul": [{"kind": "direct", "via": []}],
        "gg_finance_write": [{"kind": "nested", "group": "GG_Finance_Write", "via": ["GG_Compta", "GG_Finance_Write"], "depth": 1}],
        "gg_compta": [{"kind": "group", "group": "GG_Compta", "via": ["GG_Compta"], "depth": 0}],
    }
    rows = [
        {"storage_root_id": 2, "name": "Finance", "principal": "CORP\\GG_Finance_Write", "principal_key": "gg_finance_write",
         "raw": "ALLOWED/OI|CI/RWXD", "discovered_permissions_json": {"discovered_at": "2026-11-20T10:00:00", "control": "SR|PD|DP"}},
        {"storage_root_id": 2, "name": "Finance", "principal": "CORP\\GG_Compta", "principal_key": "gg_compta", "raw": "ALLOWED/OI|CI|I/READ"},
        {"storage_root_id": 1, "name": "Archives", "principal": "CORP\\paul", "principal_key": "paul", "raw": "ALLOWED/0x0/FULL"},
    ]
    items = folders_from_entries(rows, origins, [1, 2])
    assert [f["storage_root_id"] for f in items] == [1, 2]  # the order of the page
    archives, finance = items
    assert archives["grants"][0]["kind"] == "direct" and archives["ntfs_rights"] == "full" and not archives["multiple_paths"]
    assert finance["multiple_paths"] and finance["ntfs_rights"] == "modify" and finance["inheritance_broken"]
    assert [g["kind"] for g in finance["grants"]] == ["group", "nested"]
    assert finance["grants"][1]["via"] == ["GG_Compta", "GG_Finance_Write"]


def test_account_state_is_never_guessed() -> None:
    assert account_state(0, True) == "disabled"
    assert account_state(1, True) == "enabled"
    # A reading without the account state (before it was read, or an LDAP directory): unknown, not « enabled »
    assert account_state(1, False) == "unknown"
    assert account_state(None, True) == "not_in_directory"


def test_incomplete_data() -> None:
    # An entry without a readable mask stays an entry (special right); no entry: nothing given
    assert ace_info("CORP\\GG_X", None)["rights"] == "special"
    assert summarize([])["ntfs_rights"] is None and not summarize([])["multiple_paths"]


def test_acl_index_keys_match_short_names() -> None:
    rows = acl_index_rows(7, [{"principal": "CORP\\GG_Finance", "raw": "ALLOWED/OI|CI/READ"}, {"principal": "  "},
                              {"principal": "CORP/Paul.Martin", "raw": None}, "junk"])
    assert [(r["key"], r["raw"]) for r in rows] == [("gg_finance", "ALLOWED/OI|CI/READ"), ("paul.martin", None)]
    assert acl_index_rows(7, None) == []


def test_server_local_accounts_are_never_the_directory_namesakes() -> None:
    # BUILTIN\Administrateurs is the file server's local group: a user of the domain group « Administrateurs »
    # (Builtin container of the DC) does not get it; BUILTIN\Utilisateurs is « the whole company »
    from app.services.access_explorer import LOCAL_NAMESPACES, namespace

    origins = {"administrateurs": [{"kind": "group", "group": "Administrateurs", "via": ["Administrateurs"]}],
               "utilisateurs": [{"kind": "broad", "via": []}]}
    rows = [{"storage_root_id": 1, "name": "Angers", "principal": "BUILTIN\\Administrateurs", "principal_key": "administrateurs", "raw": "ALLOWED/OI|CI|I/FULL"},
            {"storage_root_id": 1, "name": "Angers", "principal": "BUILTIN\\Utilisateurs", "principal_key": "utilisateurs", "raw": "ALLOWED/OI|CI|I/READ"}]
    [folder] = folders_from_entries(rows, origins, [1])
    assert [g["kind"] for g in folder["grants"]] == ["broad"] and folder["ntfs_rights"] == "read"
    assert namespace("AUTORITE NT\\Système") in LOCAL_NAMESPACES and namespace("Everyone") == "" and namespace("CORP/GG_X") == "CORP"
