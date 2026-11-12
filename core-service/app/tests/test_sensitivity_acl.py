from app.services.sensitivity import _merge

OPEN = {"x": False, "o": "", "e": ["BUILTIN\\Users|R|i"], "broad": True}
CLOSED = {"x": True, "o": "", "e": ["CORP\\GG_IT|F|"], "broad": False}


def test_a_file_not_read_again_takes_the_rights_of_this_scan():
    previous = [{"path": "IT\\web.config", "category": "password", "line": 3, "acl": OPEN}]
    scan = {"findings": [{"path": "IT\\web.config", "category": "credentials_file", "line": None, "acl": CLOSED}],
            "incremental": {"read_paths": [], "gone_paths": []}}
    merged = _merge(previous, scan, same_rules=True)
    assert len(merged) == 2 and all(item["acl"] == CLOSED for item in merged)


def test_a_name_finding_does_not_lose_the_rights_of_the_content_finding():
    previous = [{"path": "a.txt", "category": "password", "line": 1, "acl": OPEN}]
    scan = {"findings": [{"path": "a.txt", "category": "password", "line": None}], "incremental": {"read_paths": [], "gone_paths": []}}
    assert _merge(previous, scan, same_rules=True)[0]["acl"] == OPEN


def test_the_rights_read_for_a_known_file_reach_its_kept_finding():
    previous = [{"path": "IT\\web.config", "category": "password", "line": 3}]
    scan = {"findings": [], "acls": [{"path": "IT\\web.config", "acl": OPEN}], "incremental": {"read_paths": [], "gone_paths": []}}
    assert _merge(previous, scan, same_rules=True)[0]["acl"] == OPEN


from app.services.sensitivity import exposed_paths, widen


def test_a_large_group_opens_a_file_like_everyone():
    closed = {"x": False, "o": "", "e": ["CORP\\GG_Tous|R|i", "CORP\\GG_IT|F|"], "broad": False, "by": []}
    item = widen([{"path": "a.txt", "category": "password", "acl": closed}], {"gg_tous": 800})[0]
    assert item["acl"]["broad"] is True and item["acl"]["by"] == ["CORP\\GG_Tous"]
    denied = {**closed, "e": ["!CORP\\GG_Tous|R|i"]}
    assert widen([{"path": "b", "acl": denied}], {"gg_tous": 800})[0]["acl"]["broad"] is False


def test_only_secret_and_personal_files_open_to_all_raise_the_alert():
    open_acl = {"broad": True, "e": [], "by": ["BUILTIN\\Users"]}
    findings = [{"path": "IT\\pw.txt", "category": "password", "acl": open_acl},
                {"path": "IT\\setup.msi", "category": "executable", "acl": open_acl},
                {"path": "IT\\key", "category": "private_key", "acl": {**open_acl, "broad": False}},
                {"path": "RH\\paie.csv", "category": "personal_data", "acl": open_acl}]
    assert exposed_paths(findings, set()) == ["IT\\pw.txt", "RH\\paie.csv"]
    assert exposed_paths(findings, {"it\\pw.txt"}) == ["RH\\paie.csv"]
