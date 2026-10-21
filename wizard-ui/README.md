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

- Toute la plateforme (Wizard compris) est configurée par un seul fichier `.env` à la racine du dépôt — voir [`.env.example`](../.env.example).

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
| réseau `b2s-app` | Réseau Podman applicatif partagé | string | `b2s-app` |
| réseau `b2s-data` | Réseau Podman DB partagé | string | `b2s-data` |
| `WIZARD_LOG_SQL_ERRORS` | Logs SQL plus verbeux | `0`, `1` | `0` |
| `WIZARD_PRIVATE_SEEDS_DIR` | Dossier de seeds privés (non commit) relatif à `backend/app/sql/` ou absolu | ex: `seeds_private` | (vide) |

## 🎭 Mode démo (DEV)

En mode DEV (`WIZARD_MODE=dev`), cocher **"Données de démonstration"** à l’étape Import exécute :

- les seeds publics : [`backend/app/sql/seeds/`](backend/app/sql/seeds/README.md)
- + (optionnel) les seeds privés non publiés si `WIZARD_PRIVATE_SEEDS_DIR` est configuré.

Un seed démo (public) est fourni : [`backend/app/sql/seeds/040_seed_demo_full.sql`](backend/app/sql/seeds/040_seed_demo_full.sql).

### Mode (DEV/PROD)

Le Wizard fonctionne en 2 modes :

- **DEV** : autorise le **seed** (`sql/seeds/`) et l’import complet.
- **PROD** : **interdit le seed** et bloque l’import tant que `force_import=true`.

Variables côté backend :

- `WIZARD_MODE=dev|prod` (prioritaire)
- ou `APP_ENV=dev|prod`

### podman-compose

Le Wizard est décrit dans le [`podman-compose.yml`](../podman-compose.yml) racine (profil `wizard`) :

1) copier [`.env.example`](../.env.example) → `.env` à la racine
2) `make wizard` (puis `make wizard-down` une fois la base initialisée)

---

## 🖼️ Captures d’écran

Les images du Wizard peuvent être ajoutées dans le dossier `images/`.

---

## 🏁 Conclusion

Le Wizard UI garantit une initialisation sécurisée, cohérente et reproductible de la plateforme BornToShare.

© BornToShare
