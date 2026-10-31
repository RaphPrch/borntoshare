"""Declare the test Active Directory in BornToShare, through its public API (as an administrator would).

    B2S_URL=https://borntoshare.example B2S_USER=admin B2S_PASSWORD_FILE=~/.b2s-admin python3 register.py

Creates, or finds when they already exist:
  - zone « AD lab » (ADLAB), access groups in OU=B2S Groups
  - identity source « AD lab » (LDAPS adlab.example.test): svc-b2s-read, provisioning account svc-b2s-prov
  - file server « AD lab file server » (SMB adlab.example.test, svc-b2s-files)
  - storage roots corp\\finance, corp\\hr, corp\\legal and projects
Passwords are stored encrypted by the application; this script never prints them.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

LAB_HOST = "adlab.example.test"
BASE_DN = "DC=example,DC=test"
GROUPS_OU = f"OU=B2S Groups,{BASE_DN}"
SERVICE_PASSWORD = os.environ.get("AD_LAB_SERVICE_PASSWORD", "Svc!Lab-2026")
ROOTS = [("Lab Finance", r"corp\finance"), ("Lab HR", r"corp\hr"), ("Lab Legal", r"corp\legal"), ("Lab Projects", "projects")]


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"HTTP {status} {code}: {message}")
        self.code = code


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        context = ssl.create_default_context()
        if os.environ.get("B2S_INSECURE") == "1":  # self-signed test certificate of BornToShare itself
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), urllib.request.HTTPSHandler(context=context)
        )

    def call(self, method: str, path: str, body: dict | None = None):
        request = urllib.request.Request(
            self.base + "/api" + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "Origin": self.base},
        )
        try:
            raw = self.opener.open(request, timeout=120).read() or b"{}"
        except urllib.error.HTTPError as exc:
            text = exc.read().decode()
            try:
                error = json.loads(text).get("error") or {}
                upstream = ((error.get("details") or {}).get("upstream_detail") or {}).get("error") or {}
                code, message = upstream.get("code") or error.get("code") or "", upstream.get("message") or error.get("message") or text
            except ValueError:
                code, message = "", text
            raise ApiError(exc.code, str(code), str(message)[:400]) from None
        payload = json.loads(raw)
        return payload.get("data", payload) if isinstance(payload, dict) else payload


def rows(value) -> list[dict]:
    if isinstance(value, dict):
        value = value.get("items") or value.get("rows") or []
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def secret(api: Api, path: str, name: str, account: str) -> str:
    stored = api.call("POST", path, {"type": "ad", "name": name, "bind_dn": account, "bind_password": SERVICE_PASSWORD})
    ref = (stored or {}).get("bind_password_ref") if isinstance(stored, dict) else None
    if not ref:
        sys.exit(f"secret {name}: no reference returned")
    return ref


def main() -> None:
    base = os.environ.get("B2S_URL", "http://127.0.0.1:3000")
    user = os.environ.get("B2S_USER", "admin")
    password_file = os.path.expanduser(os.environ.get("B2S_PASSWORD_FILE", ""))
    password = open(password_file).read().strip() if password_file else os.environ.get("B2S_PASSWORD", "")
    if not password:
        sys.exit("Set B2S_PASSWORD_FILE (or B2S_PASSWORD) to the password of a BornToShare administrator")
    api = Api(base)
    api.call("POST", "/auth/login", {"username": user, "password": password, "provider": "local"})

    zone = next((z for z in rows(api.call("GET", "/zones")) if str(z.get("code") or "").upper() == "ADLAB"), None)
    zone_id = int((zone or {}).get("id") or (zone or {}).get("zone_id") or 0)
    if not zone_id:
        zone_id = int(api.call("POST", "/zones", {"name": "AD lab", "code": "ADLAB", "description": "Test Active Directory (end-to-end tests)"})["id"])
    api.call("PUT", f"/zones/{zone_id}/provisioning-policy", {
        "enabled": True, "ou_strategy": "zone_static", "static_ou_dn": GROUPS_OU, "base_ou_dn": GROUPS_OU,
    })
    print(f"zone AD lab: #{zone_id} (groups in {GROUPS_OU})")

    source = next((s for s in rows(api.call("GET", "/identity-sources")) if s.get("name") == "AD lab"), None)
    if source:
        source_id = int(source["id"])
    else:
        read_ref = secret(api, "/identity-sources/secret-ref", f"identity-source/ldaps/{LAB_HOST}", "svc-b2s-read@example.test")
        prov_ref = secret(api, "/identity-sources/secret-ref", f"identity-source/ldaps/{LAB_HOST}/provisioning", "svc-b2s-prov@example.test")
        body = {
            "type": "ad", "name": "AD lab", "protocol": "ldaps", "host": LAB_HOST, "port": 636,
            "base_dn": BASE_DN, "domain_name": "example.test",
            "bind_dn": "svc-b2s-read@example.test", "bind_password_ref": read_ref,
            "service_accounts": {"provisioning": {"bind_dn": "svc-b2s-prov@example.test", "bind_password_ref": prov_ref}},
            "capabilities": {"auth": True, "import_groups": True, "snapshot_enabled": True, "provisioning": True},
            "auth_enabled": True, "auth_priority": 50, "is_active": True,
        }
        # LDAPS checked against the CA of the lab when it is at hand
        ca_file = os.environ.get("LAB_CA_FILE", "/export/ad-ca.pem")
        if os.path.isfile(ca_file):
            body["tls_ca_pem"] = open(ca_file, encoding="utf-8").read()
        else:
            body["tls_verify"] = False
        try:
            created = api.call("POST", "/identity-sources", body)
        except ApiError as exc:
            if exc.code != "IDENTITY_SOURCE_DOMAIN_TAKEN":
                raise
            # Another source already signs in the users of example.test: the lab serves accesses only
            print(f"note: {exc} -> AD lab declared without sign-in")
            body.update({"auth_enabled": False, "capabilities": {**body["capabilities"], "auth": False}})
            created = api.call("POST", "/identity-sources", body)
        source_id = int(created.get("id") or created.get("identity_source_id"))
    print(f"identity source AD lab: #{source_id} (ldaps://{LAB_HOST})")

    endpoint = next((e for e in rows(api.call("GET", "/storage-endpoints"))
                     if (e.get("storage_endpoint_name") or e.get("name")) == "AD lab file server"), None)
    if endpoint:
        endpoint_id = int(endpoint.get("storage_endpoint_id") or endpoint.get("id"))
    else:
        files_ref = secret(api, "/storage-endpoints/secret-ref", f"storage-endpoint/smb/{LAB_HOST}", r"EXAMPLE\svc-b2s-files")
        created = api.call("POST", "/storage-endpoints", {
            "name": "AD lab file server", "endpoint_type": "smb", "protocol": "smb", "host": LAB_HOST, "port": 445,
            "auth_type": "ntlm", "bind_dn": r"EXAMPLE\svc-b2s-files", "bind_password_ref": files_ref,
            "identity_source_id": source_id, "zone_id": zone_id, "is_active": True, "status": "active",
        })
        endpoint_id = int(created.get("id") or created.get("storage_endpoint_id"))
    print(f"file server AD lab file server: #{endpoint_id} (smb://{LAB_HOST})")

    existing = {str(r.get("root_path") or "").lower() for r in rows(api.call("GET", "/storage-roots/context"))}
    for name, rel in ROOTS:
        path = f"\\\\{LAB_HOST}\\{rel}"
        if path.lower() in existing:
            print(f"storage root {name}: already declared ({path})")
            continue
        created = api.call("POST", "/storage-roots", {"storage_endpoint_id": endpoint_id, "name": name, "root_path": path})
        print(f"storage root {name}: #{created.get('id')} ({path})")

    print("\nNext: Identity sources › AD lab › Sync now, then request an access on a Lab root as paul.martin.")


if __name__ == "__main__":
    try:
        main()
    except ApiError as exc:
        sys.exit(str(exc))
