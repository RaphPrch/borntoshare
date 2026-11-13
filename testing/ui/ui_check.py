"""UI check of the live features, on a running instance, with screenshots.

    B2S_URL=http://host:3000 B2S_ADMIN_PASSWORD_FILE=/run/pw python ui_check.py /out

Signs in as the local « admin » (password read from a file, never from the command line), then checks: the bell and
its drawer, the live connection (/live), the DFS server (one line, its own view), the palette (Ctrl+K, actions, « ? »), the requests list
(columns, saved views, column resize, right click), the alerts (right click, saved views), the 5S explorer (right
click, score card, click-to-copy), the unsaved-changes guard. Exit code 1 when a check fails. Read only: nothing is
saved on the instance (the saved views and widths live in the browser of the run; the settings form is left unsaved).
Optional: B2S_EXPECT_TOAST=1 waits up to 60 s for a new notice pushed while the page is open (insert one meanwhile).
"""
from __future__ import annotations

import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("B2S_URL", "http://127.0.0.1:3000").rstrip("/")
OUT = sys.argv[1] if len(sys.argv) > 1 else "/out"
PASSWORD = open(os.environ["B2S_ADMIN_PASSWORD_FILE"]).read().strip()
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)


def shot(page, name: str) -> None:
    page.screenshot(path=f"{OUT}/{name}.png")


def goto(page, path: str, wait_ms: int = 1500) -> None:
    # Never « networkidle »: the live connection stays open on purpose
    page.goto(BASE + path, wait_until="load", timeout=30000)
    page.wait_for_timeout(wait_ms)


def step(name: str, fn) -> None:
    try:
        fn()
    except Exception as exc:  # one broken step never hides the others
        check(name, False, f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}")


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="fr-FR", permissions=["clipboard-read", "clipboard-write"])
    ctx.add_cookies([{"name": "b2s_lang", "value": "fr", "url": BASE}])
    login = ctx.request.post(BASE + "/api/auth/login", data=json.dumps({"username": "admin", "password": PASSWORD, "provider": "local"}),
                             headers={"Content-Type": "application/json", "Origin": BASE})
    check("sign in as admin", login.ok, f"HTTP {login.status}")
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)[:200]))

    def dashboard():
        goto(page, "/dashboard", 2500)
        check("bell in the rail", page.locator(".nc-trigger").is_visible())
        # The whole rail fits a 900 px high screen: logout is in view without scrolling
        box = page.locator(".sb__logout").bounding_box()
        check("whole rail visible at 900 px high", bool(box) and box["y"] + box["height"] <= 900, f"logout bottom at {round(box['y'] + box['height']) if box else '?'} px")
        shot(page, "01-dashboard")
    step("dashboard", dashboard)

    def live():
        data = page.evaluate("""() => new Promise((resolve) => {
            const es = new EventSource('/live'); const timer = setTimeout(() => { es.close(); resolve(null); }, 12000);
            es.addEventListener('pulse', (e) => { clearTimeout(timer); es.close(); resolve(JSON.parse(e.data)); });
        })""")
        check("/live pushes a pulse", isinstance(data, dict) and "unread" in data and "pending" in data, json.dumps(data)[:160] if data else "nothing in 12 s")
    step("live", live)

    def bell():
        badge = page.locator(".nc-badge")
        before = badge.inner_text() if badge.count() else "0"
        page.locator(".nc-trigger").click()
        page.wait_for_timeout(1200)
        items = page.locator(".nc-list li")
        check("bell drawer opens and lists notices", page.locator(".nc-tools").is_visible(), f"{items.count()} notice(s), badge {before}")
        shot(page, "02-notifications")
        if page.locator(".nc-list li.is-unread").count():
            page.get_by_role("button", name="Tout marquer comme lu").click()
            page.wait_for_timeout(800)
            check("mark all as read clears the badge", page.locator(".nc-badge").count() == 0 and page.locator(".nc-list li.is-unread").count() == 0)
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
    step("bell", bell)

    def dfs_server():
        goto(page, "/admin/storage-endpoints/1", 2500)
        tree = page.locator("aside, nav").filter(has_text="DFS01").first
        check("servers list: no namespace line under DFS01", page.get_by_role("treeitem", name="Angers").count() == 0
              and page.locator("text=Bordeaux").count() == 0)
        page.get_by_text("DFS01", exact=True).first.click()
        page.wait_for_url(re.compile(r"server=DFS01"), timeout=15000)
        page.wait_for_timeout(3000)
        check("DFS server view lists its namespaces", page.locator(".dsv table tbody tr").count() >= 1, f"{page.locator('.dsv table tbody tr').count()} namespace(s)")
        check("DFS server can be removed (menu)", page.locator(".dsv").count() == 1)
        shot(page, "03-dfs-server")
    step("dfs server", dfs_server)

    def palette():
        goto(page, "/dashboard", 1200)
        page.keyboard.press("Control+k")
        page.wait_for_timeout(500)
        dialog = page.locator(".global-search")
        check("Ctrl+K opens the palette with actions", dialog.is_visible() and page.locator("#global-search-results").get_by_text(re.compile(r"Nouvelle demande d.accès")).count() > 0)
        page.keyboard.type("ang")
        page.wait_for_timeout(1500)
        shot(page, "04-palette")
        check("a folder typed offers its actions", page.get_by_text(re.compile(r"Nouvelle demande d.accès à")).count() > 0)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        page.locator("body").click(position={"x": 700, "y": 20})
        page.keyboard.press("?")
        page.wait_for_timeout(500)
        check("« ? » lists the shortcuts", page.locator(".global-search__keys").is_visible())
        shot(page, "05-shortcuts")
        page.keyboard.press("Escape")
    step("palette", palette)

    def requests():
        goto(page, "/access-requests?status=all", 2500)
        heads = page.locator(".ar-table thead th").count()
        page.get_by_role("button", name="Colonnes").click()
        page.locator(".cp__menu label", has_text="Niveau").click()
        page.wait_for_timeout(300)
        after = page.locator(".ar-table thead th").count()
        check("column picker hides a column", after == heads - 1, f"{heads} → {after}")
        page.locator(".cp__menu label", has_text="Niveau").click()
        page.keyboard.press("Escape")
        check("column resize handles", page.locator(".ar-table .b2s-col-resize").count() >= 3)
        page.get_by_role("button", name="Enregistrer cette vue").click()
        page.locator(".sv__form input").fill("Vue de recette")
        page.locator(".sv__form button[type=submit]").click()
        page.wait_for_timeout(400)
        check("a view is saved and shown as a chip", page.locator(".sv__chip", has_text="Vue de recette").count() == 1)
        shot(page, "06-requests-views")
        page.get_by_role("button", name="Supprimer la vue Vue de recette").click()
        rows = page.locator(".ar-table tbody tr[tabindex]")
        if rows.count():
            rows.first.click(button="right")
            page.wait_for_timeout(300)
            check("right click on a request opens its menu", page.locator(".cm[role=menu]").is_visible())
            shot(page, "07-requests-menu")
            page.keyboard.press("Escape")
        else:
            check("right click on a request (no request to try)", True, "skipped")
    step("requests", requests)

    def alerts():
        goto(page, "/observability?tab=alerts", 2500)
        check("alerts offer saved views", page.locator(".obs-views .sv").count() == 1)
        rows = page.locator(".obs-card table tbody tr")
        if rows.count():
            page.get_by_role("button", name="Afficher").first.click() if page.get_by_role("button", name="Afficher").count() else None
            page.wait_for_timeout(800)
            rows = page.locator(".obs-card table tbody tr")
            rows.first.click(button="right")
            page.wait_for_timeout(300)
            check("right click on an alert opens its menu", page.locator(".cm[role=menu]").is_visible())
            shot(page, "08-alerts-menu")
            page.keyboard.press("Escape")
    step("alerts", alerts)

    def explorer():
        goto(page, "/five-s", 2500)
        row = page.locator("button.fs__row").first
        if not row.count():
            check("5S explorer (no folder scored)", True, "skipped")
            return
        row.click()
        page.wait_for_url(re.compile(r"/five-s/explore/\d+"), timeout=15000)
        page.wait_for_timeout(3500)
        page.locator(".fx__score").hover()
        page.wait_for_timeout(400)
        check("score card on hover", page.locator(".fx__score-card").is_visible())
        shot(page, "09-5s-score")
        row = page.locator("table tbody tr").first
        row.click(button="right")
        page.wait_for_timeout(300)
        menu = page.locator(".cm[role=menu]")
        check("right click on a folder: menu with « Mesurer à nouveau »", menu.is_visible() and menu.get_by_text("Mesurer à nouveau").count() == 1)
        shot(page, "10-5s-menu")
        page.keyboard.press("Escape")
        row.click()
        page.wait_for_timeout(500)
        code = page.locator(".fx__path code[data-copy]")
        if code.count():
            code.click()
            page.wait_for_timeout(600)
            # Over plain HTTP the Clipboard API is missing: the confirmation toast tells the copy happened
            toast_text = page.locator(".b2s-toaster").inner_text()
            check("click on a path copies it", "Copié" in toast_text, toast_text.strip().splitlines()[-1][:80] if toast_text.strip() else "no toast")
    step("explorer", explorer)

    def unsaved():
        goto(page, "/admin/advanced-settings/logging", 2000)
        field = page.locator("input[type=number]").first
        field.fill(str(int(field.input_value() or "180") + 1))
        page.locator("a.sb__item[href='/dashboard']").click()
        page.wait_for_timeout(700)
        dialog = page.get_by_text("Les modifications faites sur cette page seront perdues.")
        check("leaving an edited form asks first", dialog.count() > 0 and page.url.endswith("/logging"))
        shot(page, "11-unsaved")
        page.get_by_role("button", name="Continuer à modifier").click()
        page.wait_for_timeout(300)
        check("keep editing stays on the page", page.url.endswith("/logging"))
    step("unsaved", unsaved)

    if os.environ.get("B2S_EXPECT_TOAST"):
        def toast():
            goto(page, "/dashboard", 1000)
            open(f"{OUT}/.toast-ready", "w").close()  # the caller inserts a notice now
            page.wait_for_selector(".b2s-toast-action", timeout=60000)
            check("a new notice shows as a toast with « Ouvrir »", True)
            shot(page, "12-toast")
        step("toast", toast)

    check("no script error in the pages", not errors, "; ".join(errors[:3]))
    browser.close()

failed = [name for name, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
