"""Demo data set on the test Active Directory: one storage root per situation, healthy ones included.

Runs like e2e_check.py (same image, same environment), after register.py:

    podman run --rm --network b2s-app -e B2S_URL=... -e B2S_USER=... -e B2S_PASSWORD_FILE=/run/pw \\
      -v <password file>:/run/pw:ro,z -v ./testing/ad-lab:/lab:ro,z --entrypoint python3 b2s-ad-lab:latest \\
      /lab/demo_seed.py [--reset] [--purge-e2e]

  --reset      removes the demo folders first (accesses revoked, folders deleted) and builds them again
  --purge-e2e  removes the « E2E e2e-… » storage roots left by e2e_check.py runs

Everything goes through BornToShare (requests, approvals, worker) except what an administrator would do by
hand on the file server or in AD (an ACE outside BornToShare, an ACE removed, a folder deleted): those are
the situations BornToShare has to detect. Folders, under \\\\adlab.example.test\\projects\\Demo:

  Finance              compliant: read and modify groups, members, guardian, tags
  Ressources humaines  compliant + a request to decide (« To review »)
  Juridique            an access ending in 5 days, another one in 20 days
  Direction            NTFS inheritance broken (badge « No inheritance »), still compliant
  Marketing            an AD group set by hand on the folder (gap to review), and a governed sub-folder
  Achats               an entry outside BornToShare, accepted
  Comptabilité         the ACE of a BornToShare group removed by hand (ACE missing)
  Archives 2019        folder deleted on the server (unreachable)
  Projets              governed, nobody has access yet
"""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2e_check as lab  # noqa: E402  (helpers: Api, ldap, smb, acl, set_ace, read_acl, snapshot…)

SHARE = "projects"
BASE = "Demo"
PEOPLE = {
    "alice.bernard": ("Alice", "Bernard"),
    "julien.durand": ("Julien", "Durand"),
    "camille.roux": ("Camille", "Roux"),
    "sophie.moreau": ("Sophie", "Moreau"),
    "lucas.petit": ("Lucas", "Petit"),
    "emma.leroy": ("Emma", "Leroy"),
    "hugo.garnier": ("Hugo", "Garnier"),
    "lea.fontaine": ("Léa", "Fontaine"),
    # Guardians (they approve the requests of their folders)
    "nathalie.girard": ("Nathalie", "Girard"),
    "olivier.bonnet": ("Olivier", "Bonnet"),
    "claire.vidal": ("Claire", "Vidal"),
}


def log(message: str) -> None:
    print(message, flush=True)


# ---------------------------------------------------------------- directory and file server (by hand)

def ensure_user(login: str) -> str:
    given, sn = PEOPLE[login]
    dn = f"CN={given} {sn},{lab.STAFF_OU}"
    lab.ldap(["ldapadd"], f"dn: {dn}\nobjectClass: user\nsAMAccountName: {login}\nuserPrincipalName: {login}@example.test\n"
                          f"givenName: {given}\nsn: {sn}\ndisplayName: {given} {sn}\n")
    pwd = base64.b64encode(f'"{lab.USER_PASSWORD}"'.encode("utf-16-le")).decode()
    lab.ldap(["ldapmodify"], f"dn: {dn}\nchangetype: modify\nreplace: unicodePwd\nunicodePwd:: {pwd}\n"
                             f"-\nreplace: userAccountControl\nuserAccountControl: 512\n")
    return dn


def ensure_group(name: str, members: list[str]) -> str:
    dn = f"CN={name},{lab.STAFF_OU}"
    if not lab.find_group(name):
        lab.create_group(name, lab.STAFF_OU)
    for member in members:
        lab.add_member(dn, member)
    return dn


def remove_ace(folder: str, group: str) -> bool:
    """Delete the ACE of a group on the folder, as an administrator would by hand."""
    line = next((l for l in lab.acl(SHARE, folder).splitlines() if l.startswith("ACL:") and f"\\{group}:" in l), None)
    if not line:
        return False
    auth = lab._auth_file("Administrator", lab.ADMIN_PASSWORD)
    try:
        subprocess.run(["smbcacls", f"//{lab.LAB}/{SHARE}", folder, "-A", auth, "-D", line], capture_output=True, text=True)
    finally:
        os.unlink(auth)
    return True


def admin_smb(command: str) -> bool:
    return lab.smb(SHARE, "Administrator", lab.ADMIN_PASSWORD, command)


# ---------------------------------------------------------------- BornToShare

def roots_under(api: lab.Api, prefix: str) -> list[dict]:
    rows = lab.rows(api.call("GET", "/storage-roots/context"))
    return [r for r in rows if str(r.get("root_path") or "").lower().startswith(prefix.lower())]


def guardian_ids(api: lab.Api, source_id: int, people: dict[str, dict], usernames: list[str]) -> list[int]:
    """Identities of directory users, imported from the AD like « Browse directory » of the guardians drawer."""
    items = [{"principal": {"type": "user", "external_id": people[u]["dn"], "dn": people[u]["dn"], "username": None,
                            "display_name": people[u].get("display_name"), "email": None}} for u in usernames]
    result = api.call("POST", "/identity/import/ad/batch", {"identity_source_id": source_id, "snapshot_source": "demo-seed", "items": items})
    rows = result.get("items") or result.get("results") or [] if isinstance(result, dict) else []
    ids = []
    for row in rows:
        identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
        value = row.get("identity_id") or row.get("id") or identity.get("identity_id") or identity.get("id")
        if value:
            ids.append(int(value))
    return ids


def new_root(api: lab.Api, endpoint_id: int, name: str, guardians: list[int]) -> int:
    folder = f"{BASE}\\{name}"
    admin_smb(f'mkdir "{BASE}"')
    admin_smb(f'mkdir "{folder}"')
    created = api.call("POST", "/storage-roots", {"storage_endpoint_id": endpoint_id, "name": name,
                                                  "root_path": f"\\\\{lab.LAB}\\{SHARE}\\{folder}"})
    root_id = int(created["id"])
    if guardians:
        api.call("PUT", f"/storage-roots/{root_id}/owners", {"guardian_ids": guardians})
    log(f"  + {name} (#{root_id})")
    return root_id


def grant(api: lab.Api, root_id: int, level: str, principal: dict, days: int | None = None) -> int:
    end = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() + days * 86400)) if days else None
    req = lab.request_access(api, root_id, level, principal, expires_at=end)
    outcome = lab.approve(api, req)
    if outcome.get("ok") is not True:
        log(f"    ! approval of {principal.get('username')} failed: {str(outcome.get('failed_reasons'))[:200]}")
    return req


def main() -> int:
    api = lab.Api()
    password_file = os.environ.get("B2S_PASSWORD_FILE", "")
    password = open(password_file).read().strip() if password_file else os.environ.get("B2S_PASSWORD", "")
    api.call("POST", "/auth/login", {"username": os.environ.get("B2S_USER", "admin"), "password": password, "provider": "local"})
    source = next((s for s in lab.rows(api.call("GET", "/identity-sources")) if s.get("name") == "AD lab"), None)
    endpoint = next((e for e in lab.rows(api.call("GET", "/storage-endpoints"))
                     if (e.get("storage_endpoint_name") or e.get("name")) == "AD lab file server"), None)
    if not (source and endpoint):
        log("Run register.py first (AD lab source and file server not found)")
        return 2
    source_id = int(source["id"])
    endpoint_id = int(endpoint.get("storage_endpoint_id") or endpoint.get("id"))
    demo_prefix = f"\\\\{lab.LAB}\\{SHARE}\\{BASE}\\"

    if "--purge-e2e" in sys.argv:
        leftovers = [r for r in lab.rows(api.call("GET", "/storage-roots/context")) if str(r.get("storage_root_name") or "").startswith("E2E e2e-")]
        log(f"Purge of {len(leftovers)} storage root(s) left by e2e_check.py")
        lab.purge(api, leftovers)

    existing = roots_under(api, demo_prefix)
    if existing and "--reset" not in sys.argv:
        log(f"The demo exists ({len(existing)} storage roots): --reset builds it again")
        return 0
    if existing:
        log(f"Reset: {len(existing)} demo storage root(s)")
        lab.purge(api, existing)

    log("People and groups in AD")
    dns = {login: ensure_user(login) for login in PEOPLE}
    ensure_group("GG_Marketing_Agence", [dns["lucas.petit"], dns["lea.fontaine"]])
    ensure_group("GG_Achats_Prestataires", [dns["hugo.garnier"]])
    lab.snapshot(api, source_id)
    people = {login: lab.principal_of(api, source_id, login) for login in PEOPLE}
    if not all(people.values()):
        # The sync may have started before the accounts were created: one more
        lab.snapshot(api, source_id)
        people = {login: lab.principal_of(api, source_id, login) for login in PEOPLE}
    missing = [login for login, principal in people.items() if not principal]
    if missing:
        log(f"Not found by BornToShare after the snapshot: {', '.join(missing)}")
        return 1

    log("Guardians imported from the directory")
    g = dict(zip(["nathalie.girard", "olivier.bonnet", "claire.vidal"],
                 guardian_ids(api, source_id, people, ["nathalie.girard", "olivier.bonnet", "claire.vidal"])))
    G = lambda *names: [g[n] for n in names if n in g]  # noqa: E731
    log(f"  {', '.join(g) or 'none imported'}")

    log("Storage roots")
    roots: dict[str, int] = {}

    roots["Finance"] = new_root(api, endpoint_id, "Finance", G("olivier.bonnet", "claire.vidal"))
    grant(api, roots["Finance"], "read", people["alice.bernard"])
    grant(api, roots["Finance"], "read", people["emma.leroy"])
    grant(api, roots["Finance"], "write", people["julien.durand"])

    roots["Ressources humaines"] = new_root(api, endpoint_id, "Ressources humaines", G("nathalie.girard"))
    grant(api, roots["Ressources humaines"], "read", people["sophie.moreau"])
    lab.request_access(api, roots["Ressources humaines"], "write", people["camille.roux"])  # left to decide

    roots["Juridique"] = new_root(api, endpoint_id, "Juridique", G("claire.vidal"))
    grant(api, roots["Juridique"], "read", people["sophie.moreau"], days=5)
    grant(api, roots["Juridique"], "write", people["alice.bernard"], days=20)

    roots["Direction"] = new_root(api, endpoint_id, "Direction", G("olivier.bonnet"))
    grant(api, roots["Direction"], "write", people["emma.leroy"])
    api.call("POST", f"/storage-roots/{roots['Direction']}/inheritance", {"mode": "break"})

    roots["Marketing"] = new_root(api, endpoint_id, "Marketing", G("nathalie.girard"))
    grant(api, roots["Marketing"], "write", people["camille.roux"])
    lab.set_ace(SHARE, f"{BASE}\\Marketing", "EXAMPLE\\GG_Marketing_Agence:ALLOWED/OI|CI/READ")
    sub = api.call("POST", f"/storage-roots/{roots['Marketing']}/subfolders", {"name": "Campagnes", "register": True})
    roots["Marketing\\Campagnes"] = int(sub.get("storage_root_id") or 0)

    roots["Achats"] = new_root(api, endpoint_id, "Achats", G("olivier.bonnet"))
    grant(api, roots["Achats"], "read", people["julien.durand"])
    lab.set_ace(SHARE, f"{BASE}\\Achats", "EXAMPLE\\GG_Achats_Prestataires:ALLOWED/OI|CI/READ")

    roots["Comptabilité"] = new_root(api, endpoint_id, "Comptabilité", G("olivier.bonnet"))
    req = grant(api, roots["Comptabilité"], "read", people["lucas.petit"])
    group = (api.call("GET", f"/access-requests/{req}/approval-preview").get("items") or [{}])[0].get("group_name") or ""
    remove_ace(f"{BASE}\\Comptabilité", group)

    roots["Archives 2019"] = new_root(api, endpoint_id, "Archives 2019", G("claire.vidal"))
    admin_smb(f'deltree "{BASE}\\Archives 2019"')

    roots["Projets"] = new_root(api, endpoint_id, "Projets", G("nathalie.girard"))

    log("Directory sync, then the ACL of every folder read on the file server")
    lab.snapshot(api, source_id)
    for name, root_id in roots.items():
        if root_id:
            lab.read_acl(api, root_id)

    # An entry outside BornToShare accepted by an administrator
    perms = api.call("GET", f"/storage-roots/{roots['Achats']}/permissions")
    gap = next((g for g in perms.get("gaps", []) if "gg_achats_prestataires" in str(g.get("principal")).lower()), None)
    if gap:
        api.call("POST", f"/storage-roots/{roots['Achats']}/permissions/exceptions", {"principal": gap["principal"], "note": "Prestataire sous contrat"})

    log("\nResult")
    log(f"  {'Folder':<22} {'ACL':<13} {'People':>6}  {'Inheritance':<12} Probe")
    context = {int(r["storage_root_id"]): r for r in roots_under(api, demo_prefix)}
    for name, root_id in roots.items():
        if not root_id:
            continue
        perms = api.call("GET", f"/storage-roots/{root_id}/permissions")
        row = context.get(root_id, {})
        inheritance = "broken" if row.get("inheritance_broken") else "inherited" if row.get("inheritance_broken") is False else "unknown"
        log(f"  {name:<22} {perms.get('status', ''):<13} {perms.get('summary', {}).get('people', 0):>6}  {inheritance:<12} {row.get('last_probe_status')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
