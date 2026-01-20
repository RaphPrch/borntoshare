from fastapi import APIRouter, HTTPException
from pathlib import Path
import json
import time
import os

router = APIRouter(prefix="/api/runtime", tags=["runtime"])

# Emplacement standardisé dans wizard-container
BASE_OUTPUT = Path("/opt/wizard/output")


# --------------------------------------------------------------
# Ensure output directory exists
# --------------------------------------------------------------
def ensure_output_dir() -> Path:
    try:
        BASE_OUTPUT.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(500, f"Impossible de créer /output : {exc}")
    return BASE_OUTPUT


# --------------------------------------------------------------
# Generate Ansible Pack
# --------------------------------------------------------------
@router.post("/generate-ansible")
async def generate_ansible_pack(config: dict):
    """
    Génère le bundle runtime BornToShare :
      - b2s-runtime-manifest.json
      - inventory.ini
      - group_vars/all.yml
      - deploy_borntoshare.yml
    """
    if not isinstance(config, dict):
        raise HTTPException(400, "Config JSON invalide")

    out_dir = ensure_output_dir()

    # ----------------------------------------------------------
    # 1. MANIFEST JSON FINAL
    # ----------------------------------------------------------
    manifest_path = out_dir / "b2s-runtime-manifest.json"

    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    # ----------------------------------------------------------
    # 2. INVENTORY MINIMAL
    # ----------------------------------------------------------
    inventory_path = out_dir / "inventory.ini"
    inventory_path.write_text(
        "[borntoshare]\nlocalhost ansible_connection=local\n",
        encoding="utf-8",
    )

    # ----------------------------------------------------------
    # 3. GROUP VARS - Synthèse complète depuis Wizard
    # ----------------------------------------------------------
    group_vars_dir = out_dir / "group_vars"
    group_vars_dir.mkdir(exist_ok=True)

    group_all_path = group_vars_dir / "all.yml"

    db_root = config.get("db_root") or {}
    db_app  = config.get("db_app") or {}
    db_name = config.get("db_name", "borntoshare")

    syslog = config.get("syslog") or {}
    smtp   = config.get("smtp") or {}
    idp    = config.get("idp") or {}
    domain = config.get("domain") or {}

    ports  = config.get("ports") or {}

    group_all_content = f"""---
# ======================================================================
# BornToShare – Variables globale générées par le Wizard (runtime)
# ======================================================================

# --------------------------
# DATABASE
# --------------------------
b2s_db_host: {db_root.get("host", "db_api")}
b2s_db_port: {db_root.get("port", 3306)}
b2s_db_name: {db_name}
b2s_db_user: {db_app.get("user", "b2s")}
b2s_db_password: "{db_app.get("password", "")}"

# --------------------------
# SYSLOG
# --------------------------
b2s_syslog_host: "{syslog.get("host", "")}"
b2s_syslog_port: "{syslog.get("port", "")}"
b2s_syslog_protocol: "{syslog.get("protocol", "")}"

# --------------------------
# SMTP
# --------------------------
b2s_smtp_host: "{smtp.get("host", "")}"
b2s_smtp_port: "{smtp.get("port", "")}"
b2s_smtp_user: "{smtp.get("user", "")}"
b2s_smtp_password: "{smtp.get("password", "")}"

# --------------------------
# IDENTITY PROVIDER / KEYCLOAK
# --------------------------
b2s_idp_url: "{idp.get("url", "")}"
b2s_idp_realm: "{idp.get("realm", "")}"
b2s_idp_client_id: "{idp.get("client_id", "")}"
b2s_idp_client_secret: "{idp.get("client_secret", "")}"

# --------------------------
# DOMAIN / LDAP / KERBEROS
# --------------------------
b2s_domain_dns_name: "{domain.get("dns_name", "")}"
b2s_domain_forest: "{domain.get("forest_name", "")}"

# Les contrôleurs de domaine sont transmis dans le manifest uniquement
# (trop dynamiques pour être stockés ici)

# --------------------------
# PORTS DES CONTENEURS (Wizard)
# --------------------------
b2s_port_auth: {ports.get("auth", 8001)}
b2s_port_gov: {ports.get("governance", 8002)}
b2s_port_gateway: {ports.get("gateway", 8080)}
b2s_port_frontend: {ports.get("frontend", 8081)}

"""
    group_all_path.write_text(group_all_content, encoding="utf-8")

    # ----------------------------------------------------------
    # 4. PLAYBOOK Ansible — exploitable
    # ----------------------------------------------------------
    playbook_path = out_dir / "deploy_borntoshare.yml"

    playbook_content = f"""---
- name: Déployer BornToShare (Podman)
  hosts: borntoshare
  become: false
  vars_files:
    - group_vars/all.yml

  tasks:

    - name: Afficher le manifest runtime
      ansible.builtin.debug:
        msg: "Manifest runtime généré → b2s-runtime-manifest.json"

    - name: Charger la configuration BornToShare
      ansible.builtin.set_fact:
        b2s_runtime: "{{ lookup('file', '{manifest_path.name}') | from_json }}"

    # -------------------------------------------------------------------
    # Exemple fictif : création d'un réseau Podman
    # À adapter selon la topologie que tu valides ensuite
    # -------------------------------------------------------------------
    - name: Créer réseau BornToShare
      containers.podman.podman_network:
        name: b2s_net
        state: present

    # -------------------------------------------------------------------
    # Exemple fictif : conteneur auth-service
    # Ici les ports proviennent du wizard
    # -------------------------------------------------------------------
    - name: Déployer auth-service
      containers.podman.podman_container:
        name: auth-service
        image: ghcr.io/borntoshare/auth-service:latest
        state: started
        recreate: true
        network: b2s_net
        publish:
          - "{{ b2s_port_auth }}:8000"
        env:
          APP_ENV: prod
          DB_HOST: "{{ b2s_db_host }}"
          DB_PORT: "{{ b2s_db_port }}"
          DB_USER: "{{ b2s_db_user }}"
          DB_PASSWORD: "{{ b2s_db_password }}"
          DB_NAME: "{{ b2s_db_name }}"

    # TODO : governance-service, gateway-service, frontend-service…
"""
    playbook_path.write_text(playbook_content, encoding="utf-8")

    return {
        "ok": True,
        "message": "Pack Ansible généré dans /opt/wizard/output.",
        "files": [
            str(manifest_path),
            str(inventory_path),
            str(group_all_path),
            str(playbook_path),
        ],
    }


# --------------------------------------------------------------
# TRIGGER DEPLOY (watcher)
# --------------------------------------------------------------
@router.post("/trigger-deploy")
async def trigger_deploy():
    out_dir = ensure_output_dir()
    signal_path = out_dir / "run_services.signal"
    content = f"trigger at {time.strftime('%Y-%m-%d %H:%M:%S')}"
    signal_path.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "message": "Signal de déploiement généré.",
        "file": str(signal_path),
    }

@router.post("/test-port")
async def test_port(payload: dict):
    import socket, time

    host = payload.get("host")
    port = int(payload.get("port", 0))
    protocol = payload.get("protocol", "tcp")

    if not host or not port:
        return {"ok": False, "error": "host et port requis"}

    start = time.time()

    try:
        if protocol == "tcp":
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.5)
            s.connect((host, port))
            s.close()
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(b"ping", (host, port))
            s.close()

        latency = round((time.time() - start) * 1000, 2)
        return {"ok": True, "latency_ms": latency}

    except Exception as e:
        return {"ok": False, "error": str(e)}
