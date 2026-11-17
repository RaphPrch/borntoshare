"""Where BornToShare runs, and the settings the wizard can set before the first start (e-mail, syslog).

Three ways to install, each checked here and turned into .env lines (read by scripts/deploy.sh, never a password):

- containers  every service and the web interface in Podman on this host (the web interface on a published port);
- hybrid      the services in Podman; the web interface a Node.js service published by Apache httpd, on this host or
              on an annex web server (then the ports of auth and core are published here, open to that server only);
- native      every service a systemd unit with its own Python environment, Redis of the system, the web interface
              published by httpd (on this host or an annex web server).

The e-mail (SMTP) and syslog settings are kept for the first start of the core: it checks and records them itself
(its password store needs its master key, made by the deployment). The SMTP password waits in SECRETS_DIR (0600).
"""
from __future__ import annotations

import ipaddress
import re
import smtplib
import socket
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

MODES = ("containers", "hybrid", "native")
_HOST = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")
_PATH = re.compile(r"^/[A-Za-z0-9._/-]{1,250}$")
_USER = re.compile(r"^[a-z_][a-z0-9_.-]{0,31}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SMTP_SECURITY = ("starttls", "tls", "none")
SYSLOG_TRANSPORTS = ("udp", "tcp", "tls")
SYSLOG_FORMATS = ("rfc5424", "cef", "json")
SYSLOG_FACILITIES = ("local0", "local1", "local2", "local3", "local4", "local5", "local6", "local7", "user", "auth", "daemon")
SEVERITIES = ("info", "warning", "high", "critical")
# Ports of the services published to the annex web server (hybrid), or their local ports (native)
DEFAULT_PORTS = {"auth": 8101, "core": 8102, "fives": 8105}


class PlanError(ValueError):
    pass


def _host(value: Any, label: str) -> str:
    text = str(value or "").strip()
    try:
        ipaddress.ip_address(text)
        return text
    except ValueError:
        pass
    if not _HOST.match(text):
        raise PlanError(f"{label} : un nom d'hôte ou une adresse IP.")
    return text


def _port(value: Any, label: str, default: int) -> int:
    try:
        port = int(value if value not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise PlanError(f"{label} : un port de 1 à 65535.") from exc
    if not 1 <= port <= 65535:
        raise PlanError(f"{label} : un port de 1 à 65535.")
    return port


def _path(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not _PATH.match(text) or "/../" in text or text.endswith("/.."):
        raise PlanError(f"{label} : un chemin absolu (lettres, chiffres, . _ - /).")
    return text


def _origin(value: Any) -> str:
    text = str(value or "").strip().rstrip("/")
    match = re.match(r"^(https?)://([^/:\s]+)(?::(\d{1,5}))?$", text)
    if not match:
        raise PlanError("Adresse publique : https://nom[:port], sans chemin.")
    _host(match.group(2), "Adresse publique")
    if match.group(3):
        _port(match.group(3), "Adresse publique", 443)
    return text


def validate_deploy(raw: dict[str, Any] | None, fives: bool) -> dict[str, Any] | None:
    """The deployment checked and normalized (None: not given, the .env stays as it is)."""
    if not raw:
        return None
    mode = str(raw.get("mode") or "containers")
    if mode not in MODES:
        raise PlanError("Type d'installation : conteneurs, hybride ou sans conteneur.")
    out: dict[str, Any] = {"mode": mode}
    web = raw.get("web") or {}
    if mode == "containers":
        out["web"] = {"origin": _origin(web.get("origin")), "published_port": _port(web.get("published_port"), "Port publié", 3000)}
        return out
    location = "annex" if web.get("location") == "annex" else "local"
    server_name = _host(web.get("server_name"), "Nom d'hôte de l'interface")
    https_port = _port(web.get("https_port"), "Port HTTPS", 443)
    out["web"] = {
        "location": location, "server_name": server_name, "https_port": https_port,
        "cert": _path(web.get("cert"), "Certificat"), "key": _path(web.get("key"), "Clé privée"),
        "origin": f"https://{server_name}" + ("" if https_port == 443 else f":{https_port}"),
    }
    ports = {name: _port((raw.get("network") or {}).get(f"{name}_port"), f"Port {name}", default) for name, default in DEFAULT_PORTS.items()}
    if len(set(ports.values())) != len(ports):
        raise PlanError("Chaque service a son propre port.")
    network: dict[str, Any] = {"ports": ports}
    if location == "annex":
        net = raw.get("network") or {}
        network.update({
            "web_host": _host(net.get("web_host"), "Serveur annexe"),
            "web_ip": str(ipaddress.ip_address(str(net.get("web_ip") or "").strip())) if _is_ip(net.get("web_ip")) else _fail("Adresse IP du serveur annexe : une adresse IP (règle de pare-feu)."),
            "api_host": _host(net.get("api_host"), "Ce serveur, vu de l'annexe"),
            "push": "bundle" if net.get("push") == "bundle" else "ssh",
        })
        if network["push"] == "ssh":
            user = str(net.get("ssh_user") or "").strip()
            if not _USER.match(user) or user == "root":
                raise PlanError("Compte SSH : un compte avec sudo, pas root.")
            key = str(net.get("ssh_key") or "").strip()
            if not re.match(r"^(~/|/)[A-Za-z0-9._/-]{1,250}$", key):
                raise PlanError("Clé SSH : un chemin sur ce serveur (~/.ssh/id_ed25519).")
            network.update({"ssh_user": user, "ssh_key": key})
    out["network"] = network
    out["fives"] = bool(fives)
    return out


def _is_ip(value: Any) -> bool:
    try:
        ipaddress.ip_address(str(value or "").strip())
        return True
    except ValueError:
        return False


def _fail(message: str) -> str:
    raise PlanError(message)


def env_lines(deploy: dict[str, Any] | None) -> list[list[str]]:
    """The .env lines of the deployment (no password): scripts/deploy.sh follows B2S_DEPLOY_MODE."""
    if not deploy:
        return []
    web = deploy["web"]
    lines = [["B2S_DEPLOY_MODE", deploy["mode"]], ["FRONTEND_PUBLIC_ORIGIN", web["origin"]]]
    if deploy["mode"] == "containers":
        return lines + [["FRONTEND_PUBLISHED_PORT", str(web["published_port"])]]
    net = deploy["network"]
    lines += [["B2S_WEB_LOCATION", web["location"]], ["B2S_WEB_SERVER_NAME", web["server_name"]], ["B2S_WEB_HTTPS_PORT", str(web["https_port"])],
              ["B2S_WEB_CERT", web["cert"]], ["B2S_WEB_KEY", web["key"]],
              ["B2S_AUTH_PORT", str(net["ports"]["auth"])], ["B2S_CORE_PORT", str(net["ports"]["core"])], ["B2S_FIVES_PORT", str(net["ports"]["fives"])]]
    if web["location"] == "annex":
        lines += [["B2S_WEB_HOST", net["web_host"]], ["B2S_WEB_IP", net["web_ip"]], ["B2S_API_HOST", net["api_host"]], ["B2S_WEB_PUSH", net["push"]]]
        if net["push"] == "ssh":
            lines += [["B2S_WEB_SSH_USER", net["ssh_user"]], ["B2S_WEB_SSH_KEY", net["ssh_key"]]]
    return lines


# ---- e-mail and syslog ------------------------------------------------------------------------------------------

def validate_smtp(raw: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str]:
    """(settings for Advanced settings › Notifications, password); None: left for later."""
    if not raw:
        return None, ""
    security = str(raw.get("security") or "starttls")
    if security not in SMTP_SECURITY:
        raise PlanError("Messagerie : sécurité STARTTLS, TLS ou aucune.")
    sender = str(raw.get("sender") or "").strip()
    if not _EMAIL.match(sender):
        raise PlanError("Messagerie : une adresse d'expéditeur.")
    username = str(raw.get("username") or "").strip()[:190]
    password = str(raw.get("password") or "")
    if len(password) > 512 or "\n" in password:
        raise PlanError("Messagerie : mot de passe trop long.")
    return {"enabled": True, "host": _host(raw.get("host"), "Serveur SMTP"), "port": _port(raw.get("port"), "Port SMTP", 587),
            "security": security, "sender": sender, "username": username}, password


def validate_syslog(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Config of the syslog extension (Advanced settings › Extensions); None: left for later."""
    if not raw:
        return None
    transport, fmt, facility = str(raw.get("transport") or "udp"), str(raw.get("format") or "rfc5424"), str(raw.get("facility") or "local4")
    if transport not in SYSLOG_TRANSPORTS or fmt not in SYSLOG_FORMATS or facility not in SYSLOG_FACILITIES:
        raise PlanError("Syslog : transport UDP, TCP ou TLS ; format RFC 5424, CEF ou JSON.")
    severity = str(raw.get("min_severity") or "high")
    if severity not in SEVERITIES:
        raise PlanError("Syslog : gravité minimale des alertes inconnue.")
    audit, alerts = bool(raw.get("audit", True)), bool(raw.get("alerts", True))
    if not audit and not alerts:
        raise PlanError("Syslog : choisir le journal d'audit, les alertes, ou les deux.")
    return {"config": {"host": _host(raw.get("host"), "Collecteur syslog"), "port": _port(raw.get("port"), "Port syslog", 514),
                       "transport": transport, "format": fmt, "facility": facility, "app_name": "borntoshare"},
            "routes": {"audit": audit, "alerts": alerts, "min_severity": severity, "categories": None, "failures_only": False}}


def send_test_mail(smtp: dict[str, Any], password: str, to: str) -> str:
    if not _EMAIL.match(str(to or "").strip()):
        raise PlanError("Test : une adresse de destination.")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = smtp["sender"], to.strip(), "BornToShare : e-mail de test de l'installation"
    message.set_content("Cet e-mail confirme que BornToShare pourra envoyer ses messages par ce serveur SMTP.\n")
    context = ssl.create_default_context()
    client: smtplib.SMTP = (smtplib.SMTP_SSL(smtp["host"], smtp["port"], timeout=15, context=context) if smtp["security"] == "tls"
                            else smtplib.SMTP(smtp["host"], smtp["port"], timeout=15))
    with client:
        if smtp["security"] == "starttls":
            client.starttls(context=context)
        if smtp["username"] and password:
            client.login(smtp["username"], password)
        client.send_message(message)
    return f"envoyé à {to.strip()} par {smtp['host']}:{smtp['port']}"


_FACILITY_CODES = {"user": 1, "daemon": 3, "auth": 4, **{f"local{i}": 16 + i for i in range(8)}}


def send_test_syslog(syslog: dict[str, Any]) -> str:
    config = syslog["config"]
    pri = _FACILITY_CODES[config["facility"]] * 8 + 6
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"<{pri}>1 {at} {socket.gethostname()[:255] or '-'} borntoshare - install.test - Message de test de l'installation de BornToShare"
    data = line.encode("utf-8")
    host, port = config["host"], config["port"]
    if config["transport"] == "udp":
        with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(5)
            sock.sendto(data, (host, port))
        return f"envoyé en UDP à {host}:{port} (sans accusé de réception : vérifiez le collecteur)"
    with socket.create_connection((host, port), timeout=5) as raw:
        framed = data + b"\n"  # as the core sends them (Advanced settings › Extensions)
        if config["transport"] == "tls":
            with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as sock:
                sock.sendall(framed)
        else:
            raw.sendall(framed)
    return f"envoyé en {config['transport'].upper()} à {host}:{port}"
