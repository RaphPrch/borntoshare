[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

# BornToShare — Zero-Trust Data Governance Platform

<p align="center">
  <img src="architecture.png" width="420">
</p>

BornToShare est une plateforme **Zero Trust** de gouvernance des données,
permettant la gestion des accès NTFS, l’orchestration des workflows d'approbation,
une séparation stricte des responsabilités et des microservices sécurisés
conformes aux bonnes pratiques SecNumCloud (niveau L2/L3).

---

# 🔥 Fonctionnalités principales

- Gestion des droits NTFS (ACL Windows)
- Workflow de validation des accès
- Authentification (local, Keycloak, LDAP)
- FastAPI microservices
- Audit, traçabilité, logs centralisés
- Bases de données durcies (SecNumCloud L2/L3)
- Exécution PowerShell en conteneur isolé
- Architecture Zero-Trust / IAM dédié
- Front-end statique moderne (Caddy)
- Docker / Podman full stack

---

# 🧱 Architecture globale

```
                              ┌─────────────────────────┐
                              │      Front-end (UI)     │
                              │    core-service (Caddy) │
                              └──────────────▲──────────┘
                                             │
                                     Static HTML/CSS/JS
                                             │
                               ┌─────────────┴─────────────┐
                               │        gateway-service     │
                               │ Reverse Proxy + Routing    │
                               └───────┬─────────┬─────────┘
                                       │         │
                      ┌────────────────┘         └──────────────────┐
                      ▼                                             ▼
         ┌───────────────────────────┐                 ┌────────────────────────────┐
         │       auth-service        │                 │    governance-service       │
         │  Login / CSRF / Tokens    │                 │ IAM / Roles / Permissions   │
         └───────────────────────────┘                 └────────────────────────────┘
                      │                                             │
                      │                                             │
                      ▼                                             ▼
            ┌────────────────┐                           ┌──────────────────────┐
            │ redis-service  │                           │       db_api         │
            │ (Cache/Session)│                           │ SecNumCloud MariaDB  │
            └────────────────┘                           └──────────────────────┘
                                                                ▲
                                                                │ SQLAlchemy
                                                                │
                                                        ┌───────────────┐
                                                        │    db_iam      │
                                                        │ IAM Hardening  │
                                                        └───────────────┘

                              ┌──────────────────────────────────────────┐
                              │              first_run_service           │
                              │  Bootstrapping, secrets, admin setup     │
                              └──────────────────────────────────────────┘

                              ┌──────────────────────────────────────────┐
                              │         iam (Keycloak + Vault)           │
                              │  Identity Providers / OAuth2 / OIDC      │
                              └──────────────────────────────────────────┘

                               ┌────────────────────────────────────────┐
                               │              traefik                   │
                               │    Edge reverse proxy / TLS / Router   │
                               └────────────────────────────────────────┘
```

---

# 🗂 Microservices inclus

| Service | Description |
|--------|-------------|
| **core-service** | UI statique, login, front-end Caddy |
| **auth-service** | Authentification, CSRF, JWT, first-login |
| **governance-service** | IAM, ACL, workflows, permissions, domaines |
| **gateway-service** | Reverse API gateway |
| **first_run_service** | Initialisation, configuration secure |
| **db_api** | Base durcie SecNumCloud L3 |
| **db_iam** | Base IAM L3 (triggers, audits, cosign) |
| **iam** | Keycloak + Vault + OIDC |
| **redis-service** | Cache sessions / tokens |
| **traefik** | Edge proxy / routing |
| **docs** | Documentation MkDocs (EN/FR) |

---

# 🛡 Sécurité

- Séparation stricte des microservices
- Middlewares : CSRF, anti-replay, anti-forgery
- Séparation IAM / API / gateway
- Aucune donnée sensible dans Git (hook + règles anti-secrets)
- Bases MariaDB durcies (L2/L3)
- Logs sécurité centralisés
- Option OPA / GitOps pour ACL futures

---

# ⚙️ Installation rapide (Podman ou Docker)

### Développement

```
podman-compose -f podman-compose.yml up --build
```

### Production

```
docker compose -f compose/docker-compose.prod.yml up -d
```

---

# 🧩 Variables d’environnement

Chaque microservice inclut un fichier :

```
example.env
```

⚠️ **Ne jamais committer un `.env`**  
Un hook Git empêche automatiquement les fuites de secrets.

---

# 🧪 Tests

```
cd governance-service
pytest -vv
```

---

# 🤝 Contribuer

Voir :  
➡ **CONTRIBUTING.md**

---

# 🔐 Politique de sécurité

Voir :  
➡ **SECURITY.md**

---

# 📄 Licence

Ce projet est sous licence **APACHE 2.0**.

---

# 📦 `.gitattributes`

```
# Linguist language detection
*.py linguist-detectable=true
*.js linguist-detectable=true
*.css linguist-detectable=true
*.html linguist-detectable=true
*.yml linguist-detectable=true
*.json linguist-detectable=true
*.sql linguist-detectable=true
*.sh linguist-detectable=true

# Ignore generated content
site/* linguist-generated=true
docs/site/* linguist-generated=true
dist/* linguist-generated=true
build/* linguist-generated=true

# Normalize line endings
* text=auto eol=lf
```

---

# ❤️ BornToShare  
"Made in France. Open Governance."


