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
| 2. Bases BornToShare | `DB_NAME`, `LOGGING_DB_NAME`, compte SQL de l'application (`DB_USER`, `DB_PASSWORD`) |
| 3. Administrateur | Identifiant, e-mail (facultatif) et mot de passe du premier compte local |
| 4. Licence et modules | Clé de licence (facultative), vérifiée hors ligne ; module 5S : `FIVES_DB_NAME`, `FIVES_INVENTORY_DB_NAME`, `FIVES_DB_USER`, `FIVES_DB_PASSWORD` |
| 5. Installation | Récapitulatif, puis le résultat de chaque action et les lignes à reporter dans `.env` |

Les champs partent des noms déjà dans `.env` (`podman-compose.yml` les passe au wizard). Aucun mot de passe ne
lui est passé.

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

Les tables du module 5S sont créées par fives-service à son démarrage. Le wizard crée ses bases et son compte.

## Données

Le wizard ne crée que la structure et le premier administrateur, sans aucune donnée de démonstration. Il peut
être relancé sur des bases existantes : elles sont conservées et chaque paquet SQL s'applique à nouveau. Un compte
SQL qui existe déjà prend le mot de passe saisi.

## Sécurité

- Les mots de passe restent dans la page le temps de l'installation. Ils ne sont écrits ni sur disque ni dans les
  journaux, et les champs sont vidés à la fin.
- Le wizard n'écrit pas de `.env` : il affiche les lignes à y reporter.
- Chaque compte SQL n'a de droits que sur ses propres bases.
- Ne pas le laisser exposé : `make wizard-down` dès la fin.
