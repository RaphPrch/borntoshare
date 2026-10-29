"""End-to-end acceptance of BornToShare against the test Active Directory (testing/ad-lab).

Runs in the b2s-ad-lab image (LDAP and SMB tools), on a network that reaches both BornToShare and
adlab.example.test, after register.py:

    podman run --rm --network b2s-app -e B2S_URL=... -e B2S_USER=... -e B2S_PASSWORD_FILE=/run/pw \\
      -v <password file>:/run/pw:ro,z -v ./testing/ad-lab/e2e_check.py:/e2e.py:ro,z \\
      --entrypoint python3 b2s-ad-lab:latest /e2e.py

Each run creates its own AD users and folders (e2e-<stamp>), so it can be replayed. It checks, against
BornToShare and directly against the directory and the file server:
  1. connection: identity source and file server tests, sign-in of a directory user
  2. regular health check: the directory is checked by a real LDAPS bind, the file server by its port
  3. sync: users created in AD appear after a snapshot and after the scheduled data sync, groups too
  4. access group: created at the approval, named by the naming policy, in the OU of the zone, member added
  5. NTFS ACL on the file server: group ACE (read / modify, inherited), effective access of the user
  6. reuse of the group, zone naming override, existing group adopted, name conflict outside the OU
  7. revocation: member removed, group and ACL kept
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

LAB = "adlab.example.test"
BASE_DN = "DC=example,DC=test"
GROUPS_OU = f"OU=B2S Groups,{BASE_DN}"
STAFF_OU = f"OU=Staff,{BASE_DN}"
ADMIN_PASSWORD = os.environ.get("AD_LAB_ADMIN_PASSWORD", "Adm1n!Lab-2026")
USER_PASSWORD = os.environ.get("AD_LAB_USER_PASSWORD", "User!Lab-2026")
STAMP = time.strftime("%m%d%H%M%S")

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, bool(ok), detail))
    print(f"  {'OK ' if ok else 'KO '} {name}" + (f"  ({detail})" if detail else ""), flush=True)
    return bool(ok)


def section(title: str) -> None:
    print(f"\n== {title}", flush=True)


# ---------------------------------------------------------------- BornToShare API

class Api:
    def __init__(self) -> None:
        self.base = os.environ.get("B2S_URL", "http://127.0.0.1:3000").rstrip("/")
        self.origin = os.environ.get("B2S_ORIGIN", self.base)
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method: str, path: str, body: dict | None = None, *, raw: bool = False):
        request = urllib.request.Request(
            self.base + "/api" + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "Origin": self.origin},
        )
        try:
            payload = json.loads(self.opener.open(request, timeout=180).read() or b"{}")
            status = 200
        except urllib.error.HTTPError as exc:
            status = exc.code
            try:
                payload = json.loads(exc.read() or b"{}")
            except ValueError:
                payload = {}
        if raw:
            return status, payload
        if status >= 400:
            raise RuntimeError(f"{method} {path}: HTTP {status} {json.dumps(payload)[:300]}")
        return payload.get("data", payload) if isinstance(payload, dict) else payload


def rows(value) -> list[dict]:
    if isinstance(value, dict):
        value = value.get("items") or []
    return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []


# ---------------------------------------------------------------- directory and file server

def _auth_file(user: str, password: str) -> str:
    handle, path = tempfile.mkstemp()
    with os.fdopen(handle, "w") as f:
        f.write(f"username = {user}\npassword = {password}\ndomain = EXAMPLE\n")
    return path


def _pass_file(password: str) -> str:
    handle, path = tempfile.mkstemp()
    with os.fdopen(handle, "w") as f:
        f.write(password)
    return path


def ldap(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    """ldapsearch / ldapadd / ldapmodify as the lab Administrator (password in a file, never on the command line)."""
    pw = _pass_file(ADMIN_PASSWORD)
    try:
        return subprocess.run(
            [args[0], "-x", "-H", f"ldaps://{LAB}", "-D", "Administrator@example.test", "-y", pw, *args[1:]],
            input=stdin, capture_output=True, text=True, env={**os.environ, "LDAPTLS_REQCERT": "never"},
        )
    finally:
        os.unlink(pw)


def find_group(name: str) -> list[dict]:
    out = ldap(["ldapsearch", "-LLL", "-o", "ldif-wrap=no", "-b", BASE_DN, f"(&(objectClass=group)(sAMAccountName={name}))",
                "distinguishedName", "groupType", "member", "description"]).stdout
    groups, current = [], None
    for line in out.splitlines():
        if line.startswith("dn: "):
            current = {"dn": line[4:], "member": []}
            groups.append(current)
        elif current is not None and ": " in line:
            key, value = line.split(": ", 1)
            if key == "member":
                current["member"].append(value)
            else:
                current[key] = value
    return groups


def create_user(login: str, given: str) -> str:
    dn = f"CN={given} E2E {STAMP},{STAFF_OU}"
    ldif = (f"dn: {dn}\nobjectClass: user\nsAMAccountName: {login}\nuserPrincipalName: {login}@example.test\n"
            f"givenName: {given}\nsn: E2E\ndisplayName: {given} E2E {STAMP}\n")
    ldap(["ldapadd"], ldif)
    pwd = '"' + USER_PASSWORD + '"'
    encoded = pwd.encode("utf-16-le")
    import base64
    ldap(["ldapmodify"], f"dn: {dn}\nchangetype: modify\nreplace: unicodePwd\nunicodePwd:: {base64.b64encode(encoded).decode()}\n"
                         f"-\nreplace: userAccountControl\nuserAccountControl: 512\n")
    return dn


def add_member(group_cn_dn: str, member_dn: str) -> None:
    ldap(["ldapmodify"], f"dn: {group_cn_dn}\nchangetype: modify\nadd: member\nmember: {member_dn}\n")


def create_group(name: str, ou_dn: str) -> str:
    dn = f"CN={name},{ou_dn}"
    ldap(["ldapadd"], f"dn: {dn}\nobjectClass: group\nsAMAccountName: {name}\ngroupType: -2147483646\n")
    return dn


def smb(share: str, user: str, password: str, command: str) -> bool:
    """True when every command succeeded: smbclient exits 0 even when a -c command is refused (NT_STATUS_...)."""
    auth = _auth_file(user, password)
    try:
        done = subprocess.run(["smbclient", f"//{LAB}/{share}", "-A", auth, "-c", command], capture_output=True, text=True)
    finally:
        os.unlink(auth)
    return done.returncode == 0 and "NT_STATUS_" not in (done.stdout + done.stderr)


def acl(share: str, folder: str) -> str:
    auth = _auth_file("Administrator", ADMIN_PASSWORD)
    try:
        return subprocess.run(["smbcacls", f"//{LAB}/{share}", folder, "-A", auth], capture_output=True, text=True).stdout
    finally:
        os.unlink(auth)


# ---------------------------------------------------------------- BornToShare helpers

def wait_probe(api: Api, payload: dict) -> dict:
    job = api.call("POST", "/probes/run", payload)
    for _ in range(45):
        state = api.call("GET", f"/probes/jobs/{job['job_id']}")
        if str(state.get("status") or "").lower() in {"success", "succeeded", "failed", "partial", "timed_out", "cancelled"}:
            return state
        time.sleep(2)
    return {"status": "timeout"}


def request_access(api: Api, root_id: int, level: str, principal: dict) -> int:
    created = api.call("POST", "/access-requests", {
        "storage_root_id": root_id, "permissions": [level], "requested_principal": principal,
        "justification": f"E2E acceptance {STAMP}",
    })
    return int(created["id"])


def approve(api: Api, request_id: int) -> dict:
    return api.call("POST", "/access-requests/bulk", {"ids": [request_id], "decision": "approve"})


def journal(api: Api, request_id: int) -> list[str]:
    events = api.call("GET", f"/activity/by-target?target_type=access_request&target_id={request_id}&limit=60")
    return [str(e.get("action")) for e in rows(events)]


def add_root(api: Api, endpoint_id: int, share: str, folder: str) -> int:
    smb(share, "Administrator", ADMIN_PASSWORD, f"mkdir {folder}")
    created = api.call("POST", "/storage-roots", {
        "storage_endpoint_id": endpoint_id, "name": f"E2E {folder}", "root_path": f"\\\\{LAB}\\{share}\\{folder}",
    })
    return int(created["id"])


def principal_of(api: Api, source_id: int, login: str) -> dict | None:
    found = api.call("POST", "/identity/search", {"identity_source_id": source_id, "query": login, "principal_type": "user",
                                                 "search_scope": "subtree", "limit": 5})
    item = next((i for i in rows(found) if str(i.get("username") or "").lower() == login), None)
    if not item:
        return None
    return {"type": "user", "dn": item.get("dn"), "username": login, "display_name": item.get("display_name"),
            "identity_source_id": source_id}


# ---------------------------------------------------------------- scenario

def main() -> int:
    api = Api()
    password_file = os.environ.get("B2S_PASSWORD_FILE", "")
    password = open(password_file).read().strip() if password_file else os.environ.get("B2S_PASSWORD", "")
    api.call("POST", "/auth/login", {"username": os.environ.get("B2S_USER", "admin"), "password": password, "provider": "local"})

    source = next((s for s in rows(api.call("GET", "/identity-sources")) if s.get("name") == "AD lab"), None)
    endpoint = next((e for e in rows(api.call("GET", "/storage-endpoints"))
                     if (e.get("storage_endpoint_name") or e.get("name")) == "AD lab file server"), None)
    zone = next((z for z in rows(api.call("GET", "/zones")) if str(z.get("code") or "").upper() == "ADLAB"), None)
    if not (source and endpoint and zone):
        print("Run register.py first (AD lab source, file server and zone not found)")
        return 2
    source_id = int(source["id"])
    endpoint_id = int(endpoint.get("storage_endpoint_id") or endpoint.get("id"))
    zone_id = int(zone.get("id") or zone.get("zone_id"))
    internal = api.call("GET", f"/identity-sources/{source_id}/internal")

    section("1. Connection")
    probe = wait_probe(api, {
        "kind": "identity-source", "protocol": "ldaps", "scope": "read",
        "target": {"host": LAB, "port": 636, "base_dn": BASE_DN}, "options": {"timeout_sec": 10, "verify_tls": False},
        "context": {"identity_source_id": source_id, "ui_origin": "admin"},
        "auth": {"mode": "simple", "username": internal.get("bind_dn"), "secret_ref": internal.get("bind_password_ref")},
    })
    check("identity source test (LDAPS bind + base DN)", str(probe.get("status")).lower() in {"success", "succeeded"},
          str((probe.get("result") or {}).get("message") or probe.get("error") or "")[:120])
    probe = wait_probe(api, {
        "kind": "storage-endpoint", "protocol": "smb", "scope": "read",
        "target": {"host": LAB, "port": 445, "storage_endpoint_id": endpoint_id},
        "auth": {"mode": "ntlm", "username": endpoint.get("bind_dn"), "secret_ref": endpoint.get("bind_password_ref")},
        "options": {"timeout_sec": 20, "discover": True}, "context": {"ui_origin": "admin", "storage_endpoint_id": endpoint_id},
    })
    shares = json.dumps(probe.get("result") or {})
    check("file server test (SMB, shares listed)", str(probe.get("status")).lower() in {"success", "succeeded"} and "projects" in shares,
          str(probe.get("status")))

    section("2. Regular health check")
    api.call("POST", "/infrastructure/schedules/health_check/run")
    components: dict[str, dict] = {}
    for _ in range(15):
        time.sleep(3)
        components = {c["component"]: c for c in rows(api.call("GET", "/infrastructure/overview").get("components"))}
        directory = components.get(f"identity_source:{source_id}") or {}
        if "bind" in str(directory.get("message") or ""):
            break
    directory = components.get(f"identity_source:{source_id}") or {}
    files = components.get(f"storage_endpoint:{endpoint_id}") or {}
    check("directory checked by a real LDAPS bind", directory.get("status") == "healthy" and "bind" in str(directory.get("message")),
          str(directory.get("message")))
    check("file server reachable", files.get("status") == "healthy", str(files.get("message")))

    section("3. Users and groups sync")
    login_a, login_b, login_c = f"e2e{STAMP}a", f"e2e{STAMP}b", f"e2e{STAMP}c"
    dn_a = create_user(login_a, "Anna")
    dn_b = create_user(login_b, "Bruno")
    dn_c = create_user(login_c, "Chloe")
    add_member(f"CN=GG_Projects,{STAFF_OU}", dn_a)
    before = str(api.call("GET", f"/identity-sources/{source_id}/internal").get("last_snapshot_at") or "")
    api.call("POST", "/identity/snapshots/run", {"identity_source_id": source_id, "mode": "full", "force_full": True})
    after = before
    for _ in range(30):
        time.sleep(3)
        after = str(api.call("GET", f"/identity-sources/{source_id}/internal").get("last_snapshot_at") or "")
        if after and after != before:
            break
    check("snapshot completed", after != before, after)
    principal_a = principal_of(api, source_id, login_a)
    principal_b = principal_of(api, source_id, login_b)
    principal_c = principal_of(api, source_id, login_c)
    check("new AD users found by BornToShare", bool(principal_a and principal_b and principal_c),
          (principal_a or {}).get("dn") or "not found")
    groups = api.call("POST", "/identity/search", {"identity_source_id": source_id, "query": "GG_Projects", "principal_type": "group",
                                                  "search_scope": "subtree", "limit": 5})
    check("AD group found by BornToShare", any(str(g.get("username") or g.get("display_name") or "").lower() == "gg_projects"
                                                 for g in rows(groups)))
    if not (principal_a and principal_b and principal_c):
        return summary()

    # The scheduled data sync (Advanced Settings › Infrastructure › Schedules) snapshots the directory too
    login_d = f"e2e{STAMP}d"
    create_user(login_d, "Dora")
    before = str(api.call("GET", f"/identity-sources/{source_id}/internal").get("last_snapshot_at") or "")
    api.call("POST", "/infrastructure/schedules/data_sync/run")
    for _ in range(40):
        time.sleep(3)
        if str(api.call("GET", f"/identity-sources/{source_id}/internal").get("last_snapshot_at") or "") != before:
            break
    check("scheduled data sync imports a new AD user", principal_of(api, source_id, login_d) is not None, login_d)

    section("4. Access group created at the approval (naming policy, OU of the zone)")
    folder = f"e2e-{STAMP}-a"
    root_a = add_root(api, endpoint_id, "projects", folder)
    expected = api.call("POST", "/naming-policies/preview", {
        "zone_id": zone_id, "storage_root_path": f"\\\\{LAB}\\projects\\{folder}", "perm": "READ", "storage_root_id": root_a,
    })
    expected_name = str((expected or {}).get("samAccountName") or (expected or {}).get("group_name") or "")
    req_a = request_access(api, root_a, "read", principal_a)
    preview = api.call("GET", f"/access-requests/{req_a}/approval-preview")
    item = (preview.get("items") or [{}])[0]
    check("preview: group to create, named by the policy", item.get("group_action") == "create" and item.get("group_name") == expected_name,
          f"{item.get('group_name')} (policy: {expected_name})")
    check("preview: OU of the zone", item.get("target_ou_dn") == GROUPS_OU, str(item.get("target_ou_dn")))
    check("group absent before the approval", not find_group(expected_name))
    outcome = approve(api, req_a)
    check("approval applied", outcome.get("ok") is True, json.dumps(outcome.get("failed_reasons") or {})[:150])
    found = find_group(expected_name)
    group = found[0] if found else {}
    check("group created in the OU of the zone", group.get("dn") == f"CN={expected_name},{GROUPS_OU}", str(group.get("dn")))
    check("global security group", group.get("groupType") == "-2147483646", str(group.get("groupType")))
    check("requester is a member", dn_a in group.get("member", []))

    section("5. NTFS ACL on the file server")
    listing = acl("projects", folder)
    check("ACE of the group: read, inherited (OI|CI)", f"EXAMPLE\\{expected_name}:ALLOWED/OI|CI/READ" in listing,
          next((l for l in listing.splitlines() if expected_name in l), "no ACE"))
    check("user reads the folder", smb("projects", login_a, USER_PASSWORD, f"cd {folder}; ls"))
    check("user cannot write (read access)", not smb("projects", login_a, USER_PASSWORD, f"cd {folder}; mkdir w"))
    check("other user has no access", not smb("projects", login_b, USER_PASSWORD, f"cd {folder}; ls"))

    req_w = request_access(api, root_a, "write", principal_b)
    approve(api, req_w)
    write_group = api.call("GET", f"/access-requests/{req_w}/approval-preview").get("items", [{}])[0].get("group_name") or ""
    listing = acl("projects", folder)
    check("write level: modify ACE (RWXD)", f"EXAMPLE\\{write_group}:ALLOWED/OI|CI/RWXD" in listing, write_group)
    check("write user can create a file", smb("projects", login_b, USER_PASSWORD, f"cd {folder}; mkdir from-{login_b}"))

    section("6. Group reuse, naming override, existing groups")
    req_c = request_access(api, root_a, "read", principal_c)
    item = (api.call("GET", f"/access-requests/{req_c}/approval-preview").get("items") or [{}])[0]
    check("second request reuses the group", item.get("group_action") == "reuse" and item.get("group_name") == expected_name)
    approve(api, req_c)
    found = find_group(expected_name)
    check("still one group, two members", len(found) == 1 and len(found[0].get("member", [])) == 2,
          f"{len(found)} group(s), {len(found[0].get('member', [])) if found else 0} member(s)")

    api.call("PUT", f"/naming-policies/zones/{zone_id}", {"override_enabled": True, "group_prefix": "ADL", "template": "{PREFIX}_{ROOTCODE}_{PERM}"})
    try:
        folder_b = f"e2e-{STAMP}-b"
        root_b = add_root(api, endpoint_id, "projects", folder_b)
        req = request_access(api, root_b, "read", principal_a)
        name = (api.call("GET", f"/access-requests/{req}/approval-preview").get("items") or [{}])[0].get("group_name") or ""
        check("zone override applies to a new group", name.startswith("ADL_"), name)
        approve(api, req)
        check("group created with the overridden name", bool(find_group(name)), name)
    finally:
        api.call("PUT", f"/naming-policies/zones/{zone_id}", {"override_enabled": False, "template": None})

    folder_c = f"e2e-{STAMP}-c"
    root_c = add_root(api, endpoint_id, "projects", folder_c)
    req = request_access(api, root_c, "read", principal_a)
    name = (api.call("GET", f"/access-requests/{req}/approval-preview").get("items") or [{}])[0].get("group_name") or ""
    create_group(name, GROUPS_OU)  # made by hand in the OU before the approval
    approve(api, req)
    steps = journal(api, req)
    check("group already in the OU is reused, not duplicated", "ad_group_reused" in steps and len(find_group(name)) == 1, name)

    folder_d = f"e2e-{STAMP}-d"
    root_d = add_root(api, endpoint_id, "projects", folder_d)
    req = request_access(api, root_d, "read", principal_a)
    name = (api.call("GET", f"/access-requests/{req}/approval-preview").get("items") or [{}])[0].get("group_name") or ""
    create_group(name, STAFF_OU)  # same name, outside the OU of the zone
    outcome = approve(api, req)
    detail = (outcome.get("failed_details") or {}).get(str(req)) or (outcome.get("failed_details") or {}).get(req) or {}
    check("same name outside the OU: stopped, existing group shown", outcome.get("ok") is False and detail.get("code") == "AD_GROUP_NAME_CONFLICT",
          f"{detail.get('code')} {detail.get('existing_dn') or ''}")

    section("7. Revocation")
    outcome = api.call("POST", "/access-requests/bulk", {"ids": [req_c], "decision": "revoke"})
    found = find_group(expected_name)
    check("revoked member removed, the other kept", outcome.get("ok") is True and found and dn_c not in found[0]["member"] and dn_a in found[0]["member"])
    check("ACE kept on the folder", f"EXAMPLE\\{expected_name}:" in acl("projects", folder))

    section("8. Sign-in of a directory user")
    if not bool(api.call("GET", f"/identity-sources/{source_id}/internal").get("auth_enabled")):
        check("sign-in skipped: sign-in is disabled on the AD lab source", True, "another source signs in example.test")
    else:
        user_api = Api()
        status, _ = user_api.call("POST", "/auth/login", {"username": "marc.admin@example.test", "password": USER_PASSWORD}, raw=True)
        check("marc.admin (GG_B2S_Admins) signs in", status == 200, f"HTTP {status}")
        status, _ = Api().call("POST", "/auth/login", {"username": "marc.admin@example.test", "password": "wrong-password"}, raw=True)
        check("wrong password refused", status in (401, 403), f"HTTP {status}")
        status, _ = Api().call("POST", "/auth/login", {"username": f"{login_b}@example.test", "password": USER_PASSWORD}, raw=True)
        check("valid AD user without a BornToShare role refused", status in (401, 403), f"HTTP {status}")

    return summary()


def summary() -> int:
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    for name, _ok, detail in failed:
        print(f"  KO {name} {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
