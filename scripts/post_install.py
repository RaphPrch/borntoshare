"""Settings chosen in the wizard, recorded by the core once it runs (run by scripts/post-install.sh).

Reads on stdin {"core_url", "smtp", "smtp_password", "syslog"}; the core checks each setting as its pages do, and keeps
the SMTP password in its own store (encrypted with its master key). The token of the services is read from the
environment (INTERNAL_TOKEN), never from an argument. Prints one line per setting, never a password.
Standard library only: it runs in the core container, or with the Python of the host (installation without
container).
"""
import json
import os
import sys
import urllib.error
import urllib.request


def call(base, method, path, body):
    token = os.environ.get("INTERNAL_TOKEN", "").strip()
    if not token:
        raise SystemExit("INTERNAL_TOKEN absent")
    request = urllib.request.Request(base.rstrip("/") + path, method=method, data=json.dumps(body).encode("utf-8"), headers={
        "content-type": "application/json", "x-internal-token": token, "x-roles": "platform_admin", "x-identity-id": "1",
        "x-actor-display": "installateur"})
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
