"""Settings chosen in the wizard, recorded by the core once it runs (run by scripts/post-install.sh).

Reads on stdin {"core_url", "smtp", "smtp_password", "syslog"}; the core checks each setting as its pages do, and keeps
the SMTP password in its own store (encrypted with its master key). The tokens are read from the environment, never
from an argument: with a token per service (H4), it calls as the web interface (B2S_TOKEN_FRONTEND) for the first
administrator, signed with PRINCIPAL_SIGNING_KEY like the BFF does (whoever runs it holds .env, and so that key);
before them, with the shared INTERNAL_TOKEN. Prints one line per setting, never a password.
Standard library only: it runs in the core container, or with the Python of the host (installation without
container).
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _headers():
    token = os.environ.get("INTERNAL_TOKEN", "").strip()
    own = (os.environ.get("B2S_SERVICE_TOKEN") or os.environ.get("B2S_TOKEN_FRONTEND") or "").strip()
    key = os.environ.get("PRINCIPAL_SIGNING_KEY", "").strip()
    if not token and not own:
        raise SystemExit("INTERNAL_TOKEN absent")
    headers = {"content-type": "application/json", "x-internal-token": token, "x-roles": "platform_admin", "x-identity-id": "1",
               "x-actor-display": "installateur"}
    if own and key:
        body = _b64(json.dumps({"id": 1, "roles": ["platform_admin"], "name": "installateur", "aud": "core",
                                "exp": int(time.time()) + 60}, separators=(",", ":")).encode("utf-8"))
        headers["x-service-token"] = own
        headers["x-b2s-actor"] = body + "." + _b64(hmac.new(key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return headers


def call(base, method, path, body):
    request = urllib.request.Request(base.rstrip("/") + path, method=method, data=json.dumps(body).encode("utf-8"), headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"{path}: {error.code} {detail}") from None


def main():
    plan = json.load(sys.stdin)
    base = plan.get("core_url") or "http://127.0.0.1:8000/api"
    failed = False
    if plan.get("smtp"):
        notifications = dict(plan["smtp"])
        if plan.get("smtp_password"):
            notifications["password"] = plan["smtp_password"]
        try:
            call(base, "POST", "/admin/config/advanced", {"notifications": notifications})
            print(f"messagerie : {plan['smtp']['host']}:{plan['smtp']['port']} enregistrée"
                  + (" (mot de passe chiffré par le core)" if plan.get("smtp_password") else ""))
        except Exception as exc:
            failed = True
            print(f"messagerie : refusée ({exc})")
    if plan.get("syslog"):
        syslog = plan["syslog"]
        try:
            call(base, "PUT", "/extensions/syslog", {"enabled": True, "config": syslog["config"], "routes": syslog["routes"]})
            print(f"syslog : {syslog['config']['host']}:{syslog['config']['port']}/{syslog['config']['transport']} activé")
        except Exception as exc:
            failed = True
            print(f"syslog : refusé ({exc})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
