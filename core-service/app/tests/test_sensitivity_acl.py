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
