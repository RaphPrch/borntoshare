"""Install lab controller: plays one installation through the wizard API, then checks the result from outside.

Runs in the Playwright image (network of the lab), with the run file written by lab.sh:
  {"scenario", "wizard_url", "app_url", "plan", "drive"}  → results appended to the steps file (JSON)
« drive »: « screens » (default) plays the wizard by its screens in a browser; « api » calls its API directly.
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


def drive_screens() -> None:
    """The wizard played by its screens, as a person would: mode, prerequisites, MariaDB (a wrong password first),
    bases, interface, network (annex), modules, administrator (a weak password first), summary, then both stages."""
    from playwright.sync_api import sync_playwright

    deploy_plan = plan["deploy"]
    annex = deploy_plan["mode"] != "containers" and deploy_plan["web"].get("location") == "annex"
    shots = Path(sys.argv[2]).parent / "screens"
    shots.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(viewport={"width": 1440, "height": 1000}).new_page()
        page.set_default_timeout(30000)
        shown = lambda sid: page.locator(f'section[data-id="{sid}"]:not([hidden])')  # noqa: E731
        can_go = lambda: page.locator("#f_next").is_enabled()  # noqa: E731

        def text(sid: str) -> str:
            return " ".join(shown(sid).inner_text().split())[:500]

        def next_to(sid: str) -> None:
            if not can_go():
                raise RuntimeError(f"« Suivant » bloqué ({page.locator('#f_note').inner_text()[:200]})")
            page.click("#f_next")
            shown(sid).wait_for()

        def choose_mode():
            page.goto(wizard, wait_until="load")
            page.click(f'button.mode[data-mode="{deploy_plan["mode"]}"]')
            shown("prereq").wait_for()
            return page.locator("#w_mode").inner_text()

        def prerequisites():
            if annex:
                page.click('section[data-id="prereq"] [data-web="annex"]')
            page.wait_for_timeout(500)
            detail = text("prereq")
            next_to("db")
            return detail

        def wrong_db_password():
            server = plan["server"]
            page.fill("#s_host", server["host"]); page.fill("#s_port", str(server["port"])); page.fill("#s_user", server["user"])
            page.fill("#s_password", "not-the-password")
            page.click("#s_test")
            page.locator("#s_result.is-error").wait_for()
            if can_go():
                raise RuntimeError("« Suivant » ouvert malgré une connexion refusée")
            return "refusé : " + " ".join(page.locator("#s_result").inner_text().split())[:200] + " · Suivant bloqué"

        def database():
            page.fill("#s_password", plan["server"]["password"])
            page.click("#s_test")
            page.locator("#s_result.stats").wait_for()
            detail = " ".join(page.locator("#s_result").inner_text().split())[:200]
            next_to("bases")
            return detail

        def bases():
            app_plan = plan["app"]
            for field, key in (("a_db", "db_name"), ("a_log", "logging_db_name"), ("a_user", "user"), ("a_migrate", "migrate_user")):
                page.fill(f"#{field}", app_plan[key])
            next_to("web")
            return ", ".join(app_plan.values())

        def web_screen():
            web = deploy_plan["web"]
            if deploy_plan["mode"] == "containers":
                page.fill("#c_origin", web["origin"]); page.fill("#c_port", str(web["published_port"]))
            else:
                page.fill("#h_name", web["server_name"]); page.fill("#h_port", str(web["https_port"]))
                page.fill("#h_cert", web["cert"]); page.fill("#h_key", web["key"])
            next_to("network" if annex else "modules")
            return json.dumps(web, ensure_ascii=False)

        def network():
            net = deploy_plan["network"]
            for field, key in (("n_host", "web_host"), ("n_ip", "web_ip"), ("n_api", "api_host"), ("n_auth", "auth_port"),
                               ("n_core", "core_port"), ("n_fives", "fives_port"), ("n_user", "ssh_user"), ("n_key", "ssh_key")):
                page.fill(f"#{field}", str(net[key]))
            next_to("modules")
            return f"annexe {net['web_host']} ({net['web_ip']}), API {net['api_host']}, SSH {net['ssh_user']}"

        def modules():
            next_to("admin")
            return "gouvernance des accès"

        def weak_admin_password():
            admin = plan["admin"]
            page.fill("#u_name", admin["username"]); page.fill("#u_email", admin.get("email") or "")
            page.fill("#u_password", "court"); page.fill("#u_confirm", "court")
            if can_go():
                raise RuntimeError("« Suivant » ouvert avec un mot de passe faible")
            return "Suivant bloqué ; règles : " + " ".join(page.locator("#u_rules").inner_text().split())[:200]

        def administrator():
            page.fill("#u_password", plan["admin"]["password"]); page.fill("#u_confirm", plan["admin"]["password"])
            next_to("ready")
            return plan["admin"]["username"]

        def summary():
            page.wait_for_timeout(500)
            page.screenshot(path=str(shots / "recapitulatif.png"), full_page=True)
            return text("ready")

        def stage_one():
            page.click("#f_next")  # « Préparer »
            page.locator('section[data-id="done1"]:not([hidden]), #f_next:has-text("Relancer")').first.wait_for(timeout=600000)
            detail = " ".join(page.locator("#p1_list").inner_text().split())[:500]
            if not shown("done1").count():
                raise RuntimeError("préparation arrêtée : " + detail)
            return detail

        def stage_two():
            page.click("#f_next")  # « Suivre le déploiement »
            page.locator('section[data-id="done2"]:not([hidden]), #p2_failed:not([hidden])').first.wait_for(timeout=1800000)
            phases = " ".join(page.locator("#p2_list").inner_text().split())[:400]
            page.screenshot(path=str(shots / "fin.png"), full_page=True)
            if not shown("done2").count():
                raise RuntimeError("déploiement arrêté : " + " ".join(page.locator("#p2_log").inner_text().split())[-500:])
            return f"{phases} · {page.locator('#d2_url').inner_text()}"

        sequence = [("écran : choix du mode", choose_mode), ("écran Prérequis : aucun point bloquant", prerequisites),
                    ("écran MariaDB : mauvais mot de passe refusé", wrong_db_password), ("écran MariaDB : connexion testée", database),
                    ("écran Bases et comptes SQL", bases), ("écran Interface", web_screen)]
        if annex:
            sequence.append(("écran Réseau entre serveurs (SSH)", network))
        sequence += [("écran Modules", modules), ("écran Administrateur : mot de passe faible refusé", weak_admin_password),
                     ("écran Administrateur", administrator), ("écran Récapitulatif", summary),
                     ("étape 1 Préparer (bases, comptes, administrateur)", stage_one),
                     ("étape 2 Déploiement suivi à l'écran", stage_two)]
        for name, fn in sequence:
            if step(name, fn) is None:
                page.screenshot(path=str(shots / "echec.png"), full_page=True)
                break
        browser.close()


step("wizard: démarré", wizard_up)
if run.get("drive", "screens") == "screens":
    drive_screens()
elif step("wizard: serveur MariaDB vérifié", database_check) is not None and step("wizard: installation", install) is not None:
    step("déploiement automatique (after-wizard + deploy.sh)", deploy)
step("interface: page de connexion", login_page)
step("parcours: première connexion de l'administrateur", first_sign_in)
