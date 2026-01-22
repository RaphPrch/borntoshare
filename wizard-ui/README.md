# 🧙 BornToShare – Wizard UI

Le **Wizard UI** est l’outil officiel d’initialisation de la plateforme **BornToShare**.

Il permet de **préparer, valider et générer** l’ensemble des éléments nécessaires au premier démarrage de la plateforme, sans manipulation manuelle de fichiers sensibles.

---

## 🎯 Objectif

- Initialisation de la base de données
- Déploiement du schéma SQL et des vues
- Création des comptes applicatifs
- Génération des fichiers `.env.*`
- Validation des prérequis techniques

Le Wizard est conçu pour être utilisé **une seule fois**, lors du bootstrap initial.

---

## 🧩 Étapes couvertes

1. Présentation
2. Administrateur applicatif
3. Connexion DB (root)
4. Base & comptes applicatifs
5. Comptes services
6. Vérifications
7. Résumé global
8. Import final

Chaque étape est bloquante si invalide.

---

## 🛡️ Sécurité

- Aucun secret versionné
- Aucune valeur par défaut sensible
- Validation stricte des mots de passe
- Génération locale des fichiers `.env`

---

## ⚙️ Prérequis

- MariaDB / MySQL accessible
- Droits root DB
- Docker ou Podman
- Services BornToShare arrêtés

---

## 🚀 Lancement

```bash
docker run -p 8080:8080 borntoshare/wizard-ui
```

Accès via http://localhost:8080

---

## 📄 Fichiers générés

Le Wizard UI **ne génère pas** de fichiers `.env.*`.

- La configuration du Wizard se fait via un fichier `.env` local (non versionné) — voir [`services/wizard-ui/.env.example`](services/wizard-ui/.env.example:1).
- Les fichiers `.env` applicatifs (DAL/Auth/Governance/…) sont gérés par le déploiement de la plateforme (hors scope du Wizard UI).

---

## 📘 Variables d’environnement

### Tableau des variables

| Variable | Rôle | Valeurs possibles | Défaut |
|---|---|---:|---|
| `WIZARD_MODE` | Mode wizard (impacte UI + règles seed/import) | `dev`, `prod` | `dev` (si absent et `APP_ENV` absent) |
| `APP_ENV` | Compat legacy (fallback pour mode) | `dev`, `prod` | `dev` |
| `LOG_LEVEL` | Verbosité logs backend | `INFO`, `DEBUG`, … | `INFO` |
| `TZ` | Fuseau horaire du conteneur | ex: `Europe/Paris` | `Europe/Paris` |
| `WIZARD_PORT` | Port exposé côté host (podman-compose) | `1-65535` | `8080` |
| `APP_NET` | Nom réseau Podman applicatif (external) | string | `b2s_app_net` |
| `DB_NET` | Nom réseau Podman DB (external) | string | `b2s_db_net` |
| `WIZARD_LOG_SQL_ERRORS` | Logs SQL plus verbeux | `0`, `1` | `0` |
| `WIZARD_PRIVATE_SEEDS_DIR` | Dossier de seeds privés (non commit) relatif à `backend/app/sql/` ou absolu | ex: `seeds_private` | (vide) |

## 🎭 Mode démo (DEV)

En mode DEV (`WIZARD_MODE=dev`), cocher **"Données de démonstration"** à l’étape Import exécute :

- les seeds publics : [`backend/app/sql/seeds/`](services/wizard-ui/backend/app/sql/seeds/README.md:1)
- + (optionnel) les seeds privés non publiés si `WIZARD_PRIVATE_SEEDS_DIR` est configuré.

Un seed démo (public) est fourni : [`backend/app/sql/seeds/040_seed_demo_full.sql`](services/wizard-ui/backend/app/sql/seeds/040_seed_demo_full.sql:1).

### Mode (DEV/PROD)

Le Wizard fonctionne en 2 modes :

- **DEV** : autorise le **seed** (`sql/seeds/`) et l’import complet.
- **PROD** : **interdit le seed** et bloque l’import tant que `force_import=true`.

Variables côté backend :

- `WIZARD_MODE=dev|prod` (prioritaire)
- ou `APP_ENV=dev|prod`

Pour un lancement local, la façon la plus simple est d’utiliser un fichier `.env` (non versionné) + l’option uvicorn `--env-file`.
Un exemple est fourni : [`services/wizard-ui/.env.example`](services/wizard-ui/.env.example).

### podman-compose

Le fichier [`services/wizard-ui/podman-compose.yml`](services/wizard-ui/podman-compose.yml:1) charge les variables via `env_file: .env`.
Donc :

1) copier [`services/wizard-ui/.env.example`](services/wizard-ui/.env.example:1) → `.env`
2) exécuter `podman-compose up --build`

---

## 🖼️ Captures d’écran

Les images du Wizard peuvent être ajoutées dans le dossier `images/`.

---

## 🏁 Conclusion

Le Wizard UI garantit une initialisation sécurisée, cohérente et reproductible de la plateforme BornToShare.

© BornToShare
