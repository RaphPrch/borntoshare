# wizard-ui

Installe BornToShare, **une seule fois**, avant le premier démarrage. Il crée :
- les bases de l'application et de son journal d'audit, avec le compte SQL de l'application ;
- le premier administrateur ;
- la licence ;
- les bases du module 5S et son compte, quand la licence ouvre ce module.

Ensuite, on l'arrête : les mises à jour du schéma passent par `make deploy`.

| | |
|---|---|
| Image | `b2s-wizard-ui` (Python 3.14, FastAPI ; page statique `backend/app/static`), utilisateur 10005 |
| Port | 8080, **publié** (`WIZARD_PORT`) le temps de l'installation |
| Profil | `wizard` : ne démarre pas avec `make up` |
| Appelle | MariaDB (compte administrateur saisi à l'écran, jamais enregistré) |

## Utilisation

```bash
make wizard          # http://<hôte>:8080
# … les cinq étapes …
make wizard-down
make deploy
```

| Étape | Ce qui est demandé |
|---|---|
| 1. Serveur MariaDB | Adresse, port et compte administrateur (root) : connexion, version, droits et bases présentes |
| 2. Bases BornToShare | `DB_NAME`, `LOGGING_DB_NAME`, comptes de l'application (`DB_USER`) et des migrations (`DB_MIGRATE_USER`) |
| 3. Administrateur | Identifiant, e-mail (facultatif) et mot de passe du premier compte local |
| 4. Licence et modules | Clé de licence (facultative), vérifiée hors ligne ; module 5S : `FIVES_DB_NAME`, `FIVES_INVENTORY_DB_NAME`, `FIVES_DB_USER` |
| 5. Installation | Récapitulatif, puis le résultat de chaque action et les lignes à reporter dans `.env` |

Les champs partent des noms déjà dans `.env` (`podman-compose.yml` les passe au wizard). Seul le mot de passe
de l'administrateur MariaDB se saisit : il sert à créer les bases et les comptes, jamais enregistré.

## Comptes SQL

Un compte par usage, avec le minimum de droits ; leurs mots de passe (40 caractères) sont générés par le wizard
et écrits dans `secrets/` (`SECRETS_DIR`, fichiers 0600), jamais affichés. `make deploy` en fait des secrets
podman et supprime les fichiers.

| Compte | Droits | Utilisé par |
|---|---|---|
| `b2s_migrate` (`DB_MIGRATE_USER`) | schéma et données sur toutes les bases | le wizard (paquets SQL), `make deploy`, `make backup` |
| `b2s_core` (`DB_USER`) | lecture et écriture sur `DB_NAME` ; ajout, lecture et purge sur `LOGGING_DB_NAME` | core-service |
| `b2s_fives` (`FIVES_DB_USER`) | lecture et écriture sur les deux bases du module | fives-service, fives-scanner |

Un compte qui existe déjà reçoit un nouveau mot de passe et exactement ces droits. La dernière étape vérifie que
chaque compte ouvre ses bases et que ceux de l'application ne peuvent pas modifier le schéma.

## API

| Route | Rôle |
|---|---|
| `GET /api/defaults` | Les noms de `.env` (serveur, bases, comptes) |
| `POST /api/server/check` | Connexion avec le compte administrateur : version, droits, bases présentes |
| `POST /api/license/check` | La clé : client, échéance, modules (clés publiques de `license_keys.py`, les mêmes que core-service) |
| `POST /api/install` | Toutes les actions dans l'ordre ; s'arrête à la première erreur et dit laquelle |

## Paquets SQL

`backend/app/sql/` contient :
- `schema/` : tables et contraintes, numérotées ;
- `views/` ;
- `indexes/` ;
- `logging/` : la base d'audit.

`migrations_runner.py` les applique dans l'ordre des noms.

`scripts/deploy.sh` rejoue les paquets récents (`PACKS`) à chaque mise à jour. Un paquet doit donc pouvoir être
appliqué plusieurs fois. Une vue dont la définition change est ajoutée à `VIEWS`, puis recréée
(`CREATE OR REPLACE`).

Les tables du module 5S sont dans `sql/fives/` et `sql/fives_inventory/`, appliquées par le compte de migration
(wizard, `make deploy`) : fives-service vérifie seulement qu'elles existent.

## Données

Le wizard ne crée que la structure et le premier administrateur, sans aucune donnée de démonstration. Il peut
être relancé sur des bases existantes : elles sont conservées et chaque paquet SQL s'applique à nouveau. Un compte
SQL qui existe déjà reçoit un nouveau mot de passe généré.

## Sécurité

- Le mot de passe de l'administrateur MariaDB reste dans la page le temps de l'installation : ni sur disque, ni dans
  les journaux.
- Les mots de passe des comptes ne quittent pas le serveur : générés, écrits dans `secrets/` (0600), jamais affichés.
- Le wizard n'écrit pas de `.env` : il affiche les lignes à y reporter (des noms seulement).
- Le conteneur tourne en root pour que les fichiers de `secrets/` appartiennent à l'utilisateur de l'hôte (podman
  sans privilèges : root du conteneur = cet utilisateur).
- Ne pas le laisser exposé : `make wizard-down` dès la fin.
