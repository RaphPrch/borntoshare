"""Report of the install lab: one Markdown file per run, and a summary per installation mode (latest run of each).

    python3 report.py <cache>      → <cache>/runs/<run>/report.md and <cache>/report.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOPOLOGY = {
    "containers": "lab-db (MariaDB 11.4) · lab-app (wizard, core, auth, capsule-runner, Redis, interface : Podman)",
    "hybrid": "lab-db (MariaDB 11.4) · lab-app (wizard, core, auth, capsule-runner, Redis : Podman ; ports ouverts à l'annexe) · "
              "lab-web (annexe : systemd, httpd + mod_ssl, Node.js 22, interface poussée par SSH)",
}


def load(run: Path) -> dict:
    steps = json.loads((run / "steps.json").read_text()) if (run / "steps.json").exists() else []
    read = lambda name: (run / name).read_text().strip() if (run / name).exists() else "—"  # noqa: E731
    return {"run": run.name, "scenario": run.name.split("-", 2)[-1], "steps": steps, "commit": read("commit"),
            "duration": read("duration"), "config": sorted(p.name for p in (run / "config").glob("*")) if (run / "config").exists() else [],
            "screens": sorted(p.name for p in (run / "screens").glob("*.png")) if (run / "screens").exists() else []}


def run_report(info: dict) -> str:
    ok = sum(1 for s in info["steps"] if s["ok"])
    lines = [
        f"# Labo d'installation · {info['scenario']} · {info['run']}", "",
        f"- **Mode** : {info['scenario']}",
        f"- **Topologie** : {TOPOLOGY.get(info['scenario'], '—')}",
        f"- **Code testé** : {info['commit']} (images produit de ce commit, préchargées, sans registre ni Internet)",
        f"- **Durée totale** : {info['duration']} s",
        f"- **Résultat** : {ok}/{len(info['steps'])} étapes réussies", "",
        "| | Étape | Durée | Détail |", "|---|---|---|---|",
    ]
    for s in info["steps"]:
        detail = str(s["detail"]).replace("|", "\\|").replace("\n", " ⏎ ")[:300]
        lines.append(f"| {'✅' if s['ok'] else '❌'} | {s['step']} | {s['seconds']:.0f} s | {detail} |")
    if info["config"]:
        lines += ["", "**Fichiers de configuration conservés** (secrets masqués) : " + ", ".join(f"`config/{c}`" for c in info["config"])]
    if info["screens"]:
        lines += ["", "**Captures du wizard** : " + ", ".join(f"`screens/{c}`" for c in info["screens"])]
    failed = [s for s in info["steps"] if not s["ok"]]
    if failed:
        lines += ["", "## Échecs", ""] + [f"- **{s['step']}** : {s['detail']}" for s in failed]
    return "\n".join(lines) + "\n"


def main(cache: Path) -> None:
    runs = sorted(p for p in (cache / "runs").glob("*") if p.is_dir())
    latest: dict[str, dict] = {}
    for run in runs:
        info = load(run)
        (run / "report.md").write_text(run_report(info))
        latest[info["scenario"]] = info
    lines = ["# Labo d'installation BornToShare · synthèse par mode", "",
             "| Mode | Dernière exécution | Code | Étapes réussies | Durée | Rapport |", "|---|---|---|---|---|---|"]
    for scenario, info in sorted(latest.items()):
        ok = sum(1 for s in info["steps"] if s["ok"])
        lines.append(f"| {scenario} | {info['run']} | {info['commit']} | {ok}/{len(info['steps'])} | {info['duration']} s | runs/{info['run']}/report.md |")
    lines += ["", "| Mode | Statut |", "|---|---|", "| native | non couvert par le labo : à valider sur une vraie VM avec systemd |"]
    (cache / "report.md").write_text("\n".join(lines) + "\n")
    print((cache / "report.md").read_text())


main(Path(sys.argv[1]))
