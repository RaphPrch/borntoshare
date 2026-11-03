# wizard-ui

Initialise la base de BornToShare, **une seule fois**, à l'installation. Il crée les deux bases, le compte SQL
de l'application et le premier administrateur, puis applique tous les paquets SQL. Ensuite, on l'arrête : les
mises à jour du schéma passent par `make deploy`.

| | |
|---|---|
| Image | `b2s-wizard-ui` (Python 3.14, FastAPI ; page statique `backend/app/static`), utilisateur 10005 |
| Port | 8080, **publié** (`WIZARD_PORT`) le temps de l'installation |
| Profil | `wizard` : ne démarre pas avec `make up` |
| Appelle | MariaDB (compte root fourni à l'écran, jamais enregistré) |

## Utilisation

```bash
cp .env.example .env && chmod 600 .env     # voir docs/installation.md
make wizard                                # http://<hôte>:8080
# … les cinq étapes …
make wizard-down
```

| Étape | Ce qui est demandé |
|---|---|
| 1. Administrateur applicatif | Identifiant et mot de passe du premier compte local administrateur |
| 2. Connexion à la base | Serveur, port et compte MariaDB avec les droits de création (test de connexion et des droits) |
| 3. Base applicative | Nom de la base (`DB_NAME`), compte SQL de l'application et son mot de passe |
| 4. Base Logging | Nom de la base d'audit (`LOGGING_DB_NAME`) |
| 5. Validation | Récapitulatif, puis import |

Le compte SQL de l'étape 3 est celui à reporter dans `.env` (`DB_USER`, `DB_PASSWORD`).

## Paquets SQL

`backend/app/sql/` : `schema/` (tables et contraintes, numérotées), `views/`, `indexes/`, `logging/` (base
d'audit). `migrations_runner.py` les applique dans l'ordre des noms.
`scripts/deploy.sh` rejoue les paquets récents (`PACKS`) à chaque mise à jour : un paquet doit pouvoir être
appliqué plusieurs fois, et sa liste de valeurs autorisées doit inclure celles des paquets suivants.

## Données

Le wizard ne crée que la structure (schéma, vues, index, base d'audit) et le premier administrateur : aucune
donnée de démonstration. Il peut être relancé sur une base existante : chaque paquet SQL s'applique à nouveau
sans rien effacer.

## Sécurité

- Le mot de passe root n'est utilisé que pendant l'import et n'est jamais écrit sur disque.
- Le wizard n'écrit pas de `.env` : toute la configuration est dans le `.env` de la racine.
- Ne pas le laisser exposé : `make wizard-down` dès la fin.
