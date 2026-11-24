"""Install lab controller: plays one installation through the wizard API, then checks the result from outside.

Runs in the Playwright image (network of the lab), with the run file written by lab.sh:
  {"scenario", "wizard_url", "app_url", "plan"}  → results appended to the steps file (JSON)
Every step is recorded (name, ok, seconds, detail) even when an earlier one failed, so the report says how far it got.
"""
from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

run = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2])
steps: list[dict] = json.loads(out.read_text()) if out.exists() else []
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # lab certificates are self-signed


def save() -> None:
    out.write_text(json.dumps(steps, indent=2, ensure_ascii=False))


def step(name: str, fn) -> object:
    started = time.monotonic()
    try:
        detail, ok = fn(), True
    except Exception as exc:  # the report says why
        detail, ok = f"{type(exc).__name__}: {exc}"[:800], False
    steps.append({"step": name, "ok": ok, "seconds": round(time.monotonic() - started, 1), "detail": detail, "by": "controller"})
    save()
    print(("OK  " if ok else "KO  ") + name, "·", str(detail)[:160], flush=True)
    return detail if ok else None


def http(method: str, url: str, body: dict | None = None, timeout: int = 60) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=CTX) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw.decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:500]


wizard, app, plan = run["wizard_url"], run["app_url"], run["plan"]


def wizard_up():
    for _ in range(60):
        try:
            if http("GET", f"{wizard}/health", timeout=5)[0] == 200:
                return "le wizard répond"
        except OSError:
            pass
        time.sleep(3)
    raise RuntimeError("le wizard ne répond pas en 3 min")


def database_check():
    code, body = http("POST", f"{wizard}/api/server/check", plan["server"])
    if code != 200 or not body.get("ready"):
        raise RuntimeError(f"HTTP {code} : {body}")
    return f"MariaDB {body['version']}, {body['latency_ms']} ms, droits complets"


def install():
    code, body = http("POST", f"{wizard}/api/install", plan, timeout=600)
    if code != 200 or not body.get("ok"):
        raise RuntimeError(f"HTTP {code} : {json.dumps(body, ensure_ascii=False)[:600]}")
    return "bases, comptes, paquets SQL, administrateur : " + ", ".join(s.get("label", "?") for s in body.get("steps", []))[:400]


def deploy():
    last, deadline = None, time.monotonic() + 1800
    while time.monotonic() < deadline:
        _code, status = http("GET", f"{wizard}/api/deploy", timeout=10)
        if isinstance(status, dict):
            if status.get("phase") != (last or {}).get("phase"):
                print("    ·", status.get("state"), status.get("phase"), flush=True)
            last = status
            if status.get("state") == "done":
                return {"phases": status.get("phases"), "app_url": status.get("app_url")}
            if status.get("state") == "failed":
                raise RuntimeError(f"phase {status.get('phase')} : " + " | ".join(status.get("log") or [])[-700:])
        time.sleep(5)
    raise RuntimeError(f"déploiement non terminé en 30 min (dernier état : {last})")


def login_page():
    for _ in range(40):
        code, _body = http("GET", f"{app}/login", timeout=10)
        if code == 200:
            return f"{app}/login → 200"
        time.sleep(3)
    raise RuntimeError(f"{app}/login → {code}")


def first_sign_in():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(ignore_https_errors=True).new_page()
        errors: list[str] = []
        page.on("console", lambda m: m.type == "error" and errors.append(m.text[:120]))
        page.goto(f"{app}/login", wait_until="load")
        page.fill("input[name=username]", plan["admin"]["username"])
        page.fill("input[name=password]", plan["admin"]["password"])
        page.click(".lg__submit")
        page.wait_for_timeout(4000)
        path = page.url.split("//", 1)[-1].split("/", 1)[-1]
        browser.close()
        # A temporary password: the application asks for a new one first (/password); any other page is signed in
        if path.startswith("login"):
            raise RuntimeError(f"toujours sur /login ({errors[:2]})")
        return f"connecté, redirigé vers /{path}" + (f" · erreurs console : {errors[:2]}" if errors else "")


step("wizard: démarré", wizard_up)
if step("wizard: serveur MariaDB vérifié", database_check) is not None and step("wizard: installation", install) is not None:
    step("déploiement automatique (after-wizard + deploy.sh)", deploy)
step("interface: page de connexion", login_page)
step("parcours: première connexion de l'administrateur", first_sign_in)
