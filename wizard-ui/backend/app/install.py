"""The installation done by the wizard, in order, each action reported (done, or the error that stopped it):

1. the database of BornToShare and its audit database, and the SQL account of the application (rights on both);
2. their SQL packs (tables, views, indexes; audit);
3. the first local administrator;
4. the license key, and the modules it opens switched on;
5. for the 5S module: its two databases and its own SQL account (rights on them only; its tables are created by
   fives-service when it starts);
6. a check that each account opens its databases.

Everything can be run again on existing databases: nothing is deleted, every pack applies again. The MariaDB
administrator account is used for this call only, never written.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

from .admin_logic import create_local_admin_if_needed
from .db import get_connection
from .license import License, decode, record
from .migrations_runner import run_logging_schema_pack, run_schema_pack
from .security import validate_password_complexity

logger = logging.getLogger("wizard.install")

_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]{1,64}$")
SYSTEM_DATABASES = {"information_schema", "mysql", "performance_schema", "sys"}


class InstallError(ValueError):
    pass


def check_identifier(value: str, label: str) -> str:
    value = str(value or "").strip()
    if not _IDENTIFIER.match(value):
        raise InstallError(f"{label} : lettres, chiffres et « _ » uniquement (64 au plus).")
    if value.lower() == "root" or value.lower() in SYSTEM_DATABASES:
        raise InstallError(f"{label} : « {value} » est réservé par MariaDB.")
    return value


def check_password(value: str, label: str) -> str:
    try:
        validate_password_complexity(value)
    except ValueError as exc:
        raise InstallError(f"{label} : 12 caractères au moins, avec minuscule, majuscule, chiffre et caractère spécial.") from exc
    return value


def validate(plan: dict[str, Any]) -> dict[str, Any]:
    """The plan checked and normalized; InstallError on the first problem."""
    server, app, admin = plan.get("server") or {}, plan.get("app") or {}, plan.get("admin") or {}
    if not str(server.get("host") or "").strip() or not server.get("user") or not server.get("password"):
        raise InstallError("Serveur MariaDB : adresse, compte et mot de passe requis.")
    out: dict[str, Any] = {
        "server": {"host": str(server["host"]).strip(), "port": int(server.get("port") or 3306), "user": str(server["user"]),
                   "password": str(server["password"])},
        "app": {"db_name": check_identifier(app.get("db_name"), "Base de données"),
                "logging_db_name": check_identifier(app.get("logging_db_name"), "Base des journaux"),
                "user": check_identifier(app.get("user"), "Compte SQL de l'application"),
                "password": check_password(str(app.get("password") or ""), "Mot de passe du compte SQL de l'application")},
    }
    username = str(admin.get("username") or "").strip()
    if not username or len(username) > 190:
        raise InstallError("Administrateur : identifiant requis.")
    password = check_password(str(admin.get("password") or ""), "Mot de passe de l'administrateur")
    if username.lower() in password.lower():
        raise InstallError("Mot de passe de l'administrateur : il ne doit pas contenir l'identifiant.")
    out["admin"] = {"username": username, "email": str(admin.get("email") or "").strip() or None, "password": password}
    out["license"] = decode(plan["license"]) if plan.get("license") else None
    fives = plan.get("fives")
    if fives:
        if not out["license"] or "fives" not in out["license"].features:
            raise InstallError("Module 5S : la clé de licence ne l'ouvre pas.")
        out["fives"] = {"db_name": check_identifier(fives.get("db_name"), "Base du module 5S"),
                        "inventory_db_name": check_identifier(fives.get("inventory_db_name"), "Base d'inventaire du module 5S"),
                        "user": check_identifier(fives.get("user"), "Compte SQL du module 5S"),
                        "password": check_password(str(fives.get("password") or ""), "Mot de passe du compte SQL du module 5S")}
        if out["fives"]["user"] == out["app"]["user"]:
            raise InstallError("Le module 5S a son propre compte SQL : choisir un autre nom que celui de l'application.")
    else:
        out["fives"] = None
    names = [out["app"]["db_name"], out["app"]["logging_db_name"]] + ([out["fives"]["db_name"], out["fives"]["inventory_db_name"]] if out["fives"] else [])
    if len({name.lower() for name in names}) != len(names):
        raise InstallError("Chaque base doit avoir son propre nom.")
    return out


def check_server(server: dict[str, Any]) -> dict[str, Any]:
    """Can this account create the databases and the accounts? Its version, and the databases already there."""
    import time

    started = time.monotonic()
    conn = get_connection(root_cfg=server)
    latency = int((time.monotonic() - started) * 1000)
    cur = conn.cursor()
    try:
        cur.execute("SELECT VERSION()")
        version = str(cur.fetchone()[0])
        cur.execute("SHOW DATABASES")
        databases = sorted(str(row[0]) for row in cur.fetchall() if str(row[0]) not in SYSTEM_DATABASES)
        cur.execute("SHOW GRANTS FOR CURRENT_USER")
        grants = " ".join(str(row[0]) for row in cur.fetchall()).upper()
        all_on_all = "ALL PRIVILEGES ON *.*" in grants
        can = {
            "create_database": all_on_all or bool(re.search(r"GRANT [^\n]*\bCREATE\b[^\n]* ON \*\.\*", grants)),
            "create_user": all_on_all or "CREATE USER" in grants,
            "grant": "WITH GRANT OPTION" in grants,
        }
        return {"version": version, "latency_ms": latency, "databases": databases, "privileges": can, "ready": all(can.values())}
    finally:
        cur.close()
        conn.close()


def _account(cur, user: str, password: str, databases: list[str]) -> None:
    # The password typed is the one of the account, also when it already exists (it goes to .env)
    cur.execute(f"CREATE USER IF NOT EXISTS `{user}`@'%' IDENTIFIED BY %s", (password,))
    cur.execute(f"ALTER USER `{user}`@'%' IDENTIFIED BY %s", (password,))
    for name in databases:
        cur.execute(f"GRANT ALL PRIVILEGES ON `{name}`.* TO `{user}`@'%'")


def _create(server: dict[str, Any], databases: list[str], user: str, password: str) -> list[str]:
    """Create the databases (those already there are kept), the account and its rights; the names created."""
    conn = get_connection(root_cfg=server)
    cur = conn.cursor()
    try:
        cur.execute("SHOW DATABASES")
        existing = {str(row[0]).lower() for row in cur.fetchall()}
        for name in databases:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        _account(cur, user, password, databases)
        cur.execute("FLUSH PRIVILEGES")
        conn.commit()
        return [name for name in databases if name.lower() not in existing]
    finally:
        cur.close()
        conn.close()


def _opens(server: dict[str, Any], user: str, password: str, databases: list[str]) -> None:
    for name in databases:
        conn = get_connection(root_cfg={**server, "user": user, "password": password}, database=True, db_name=name)
        conn.close()


def _license(server: dict[str, Any], db_name: str, lic: License, by: str, switch_on: list[str]) -> None:
    conn = get_connection(root_cfg=server, database=True, db_name=db_name)
    cur = conn.cursor()
    try:
        record(cur, lic, by=by, switch_on=switch_on)
        conn.commit()
    finally:
        cur.close()
        conn.close()


def _kept(names: list[str], created: list[str]) -> str:
    kept = [name for name in names if name not in created]
    return f" ; déjà présente(s), conservée(s) : {', '.join(kept)}" if kept else ""


def run(plan: dict[str, Any]) -> dict[str, Any]:
    """Every action in order; stops at the first failure. {ok, steps: [{key, label, ok, detail}], env: [[name, value]]}."""
    server, app, admin, lic, fives = plan["server"], plan["app"], plan["admin"], plan["license"], plan["fives"]
    app_dbs = [app["db_name"], app["logging_db_name"]]
    steps: list[dict[str, Any]] = []

    def step(key: str, label: str, action: Callable[[], str | None]) -> bool:
        try:
            detail = action()
            steps.append({"key": key, "label": label, "ok": True, "detail": detail or ""})
            return True
        except Exception as exc:  # the error is shown on screen, the account passwords are never in it
            logger.exception("[INSTALL] %s failed", key)
            steps.append({"key": key, "label": label, "ok": False, "detail": str(exc)[:500]})
            return False

    def databases() -> str:
        created = _create(server, app_dbs, app["user"], app["password"])
        return f"{', '.join(app_dbs)} · compte {app['user']}" + _kept(app_dbs, created)

    def packs() -> str:
        count = run_schema_pack(app["db_name"], server)
        audit = run_logging_schema_pack(app["logging_db_name"], server)
        return f"{count} paquets sur {app['db_name']}, {audit} sur {app['logging_db_name']}"

    def administrator() -> str:
        create_local_admin_if_needed(db_name=app["db_name"], root_cfg=server, username=admin["username"], email=admin["email"],
                                     password=admin["password"])
        return f"{admin['username']} (compte local, administrateur de la plateforme)"

    def license_() -> str:
        _license(server, app["db_name"], lic, admin["username"], ["fives"] if fives else [])
        return f"{lic.customer} · {lic.key_hint}" + (" · module 5S activé" if fives else "")

    def module() -> str:
        names = [fives["db_name"], fives["inventory_db_name"]]
        created = _create(server, names, fives["user"], fives["password"])
        return f"{', '.join(names)} · compte {fives['user']}" + _kept(names, created)

    def accounts() -> str:
        _opens(server, app["user"], app["password"], app_dbs)
        if fives:
            _opens(server, fives["user"], fives["password"], [fives["db_name"], fives["inventory_db_name"]])
        return "chaque compte ouvre ses bases"

    actions: list[tuple[str, str, Callable[[], str | None]]] = [
        ("databases", "Bases de BornToShare et compte de l'application", databases),
        ("packs", "Tables, vues et index", packs),
        ("admin", "Premier administrateur", administrator),
    ]
    if lic:
        actions.append(("license", "Licence", license_))
    if fives:
        actions.append(("fives", "Bases du module 5S et son compte", module))
    actions.append(("check", "Vérification des comptes", accounts))
    ok = all(step(*action) for action in actions)

    env = [["DB_HOST", server["host"]], ["DB_PORT", str(server["port"])], ["DB_NAME", app["db_name"]], ["DB_USER", app["user"]],
           ["DB_PASSWORD", None], ["LOGGING_DB_NAME", app["logging_db_name"]]]
    if fives:
        env += [["FIVES_DB_NAME", fives["db_name"]], ["FIVES_INVENTORY_DB_NAME", fives["inventory_db_name"]],
                ["FIVES_DB_USER", fives["user"]], ["FIVES_DB_PASSWORD", None]]
    return {"ok": ok, "steps": steps, "env": env}
