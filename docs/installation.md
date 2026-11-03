# Installation et exploitation

## Prérequis

| Élément | Attendu |
|---|---|
| Hôte | Linux (RHEL 9 ou équivalent), Podman 4+ et podman-compose, `make`, `git` ; 2 vCPU, 4 Go de RAM au minimum |
| Base | MariaDB 10.6+ ou 11.x, joignable en 3306 ; un compte avec les droits de création (root) le temps du wizard |
| Réseau | Les flux de [architecture.md](architecture.md#flux-à-ouvrir-vers-lextérieur) ouverts depuis l'hôte |
| Annuaire | Un AD joignable en LDAPS (636) avec le certificat de son autorité ; un compte de service de lecture et, pour les accès, un compte délégué sur l'OU des groupes (voir [securite.md](securite.md#comptes-de-service-et-droits-à-déléguer)) |
| Serveurs de fichiers | SMB 3 (445) ; un compte administrateur local par serveur (lecture des ACL, création des partages) |
| Accès des utilisateurs | Un proxy inverse HTTPS devant le port 3000 est recommandé ; `FRONTEND_PUBLIC_ORIGIN` = son URL |

## 1. Le fichier `.env`

Un seul fichier à la racine du dépôt configure toute la pile. Il n'y a pas de mode « dev » ou « prod » : la pile se comporte toujours comme en production. Chaque conteneur ne reçoit que les variables
qu'il lit (`podman-compose.yml`).

```bash
cp .env.example .env
chmod 600 .env
```

| Variable | Lue par | Valeur |
|---|---|---|
| `INTERNAL_TOKEN` | tous | Jeton partagé entre les services, 32 caractères aléatoires au moins |
| `PRINCIPAL_SIGNING_KEY` | auth-service, frontend | Clé de signature du cookie de session, 32 caractères aléatoires au moins ; la clé par défaut est refusée |
| `DB_HOST`, `DB_PORT` | core-service | Serveur MariaDB |
| `DB_NAME`, `LOGGING_DB_NAME` | core-service | Bases des données et de l'audit (créées par le wizard) |
| `DB_USER`, `DB_PASSWORD` | core-service | Compte SQL de l'application, **celui que le wizard crée** (par défaut `b2s_app`) |
| `REDIS_PASSWORD` | redis, auth, core, worker | Mot de passe Redis, lettres et chiffres uniquement |
| `B2S_SECRET_MASTER_KEY` | core-service | 32 octets en base64 (`openssl rand -base64 32`) : chiffre les mots de passe stockés. **À sauvegarder à part** |
| `FRONTEND_PUBLIC_ORIGIN` | frontend | URL publique exacte (schéma, hôte, port) : sert de contrôle d'origine |
| `FRONTEND_PUBLISHED_PORT` | compose | Port publié sur l'hôte (3000) |
| `RUNNER_MAX_SCOPE` | worker | `write` (normal) ou `read` (worker de lecture seule) |
| `AGENT_TLS_CERT`, `AGENT_TLS_KEY` | worker | Certificat et clé PEM de l'agent du worker (sous `/etc/b2s/certs`) ; vides : HTTP sur 8080, réseau interne uniquement |
| `AGENT_PORT` | worker | Vide : 8443 en HTTPS, 8080 en HTTP |
| `B2S_AGENT_CA_FILE` | core-service | Autorité privée des certificats d'agent (ex. `/etc/b2s/certs/agent-ca.pem`) |
| `B2S_OIDC_CA_FILE` | auth-service | Autorité privée des certificats Keycloak (SSO) |
| `WIZARD_PORT` | wizard | Port du wizard |

Générer un secret : `openssl rand -base64 48 | tr -d '/+=' | cut -c1-48`.

Les fichiers de certificats (agent, autorités privées) se déposent dans `capsule-runner/certs/`, monté en
lecture seule dans `/etc/b2s/certs` par auth-service, core-service et capsule-runner.

`B2S_VERSION` n'est pas à renseigner : `make deploy` y met le commit et la date, affichés en bas du menu.

## 2. Le wizard : bases et premier administrateur

```bash
make wizard          # http://<hôte>:8080
```

Le wizard demande, étape par étape :

1. **Administrateur applicatif** : identifiant et mot de passe du premier compte local administrateur.
2. **Connexion à la base** : compte MariaDB avec les droits de création (root), utilisé une seule fois.
3. **Base applicative** : nom de la base (`DB_NAME`) et compte SQL de l'application (nom, mot de passe).
4. **Base Logging** : nom de la base d'audit (`LOGGING_DB_NAME`).
5. **Validation** : vérification des droits, puis import des paquets SQL (schéma, vues, index, journal).

Reporter ensuite dans `.env` le compte SQL créé (`DB_USER`, `DB_PASSWORD`), puis :

```bash
make wizard-down     # le wizard ne doit pas rester exposé
make up
```

## 3. Premier démarrage dans l'application

À la première connexion avec le compte administrateur, l'assistant `/setup` guide la déclaration de :
l'annuaire (LDAPS, certificat, compte de service), le premier serveur de fichiers (compte, partages trouvés),
les identités autorisées à se connecter et les administrateurs, puis les premiers dossiers gouvernés.

Ensuite, dans Réglages avancés : Réseau et DNS (serveurs DNS de chaque domaine), Infrastructure (workers,
planifications), Politique de nommage des groupes AD, Gouvernance (nombre minimal de gardiens).

## 4. Mises à jour

```bash
git pull
make deploy
```

`make deploy` (scripts/deploy.sh) :

1. applique les paquets SQL de `PACKS`, tous rejouables ;
2. étiquette les images en service `rollback-<date>` ;
3. reconstruit et recrée core, frontend, worker et auth (en passant `B2S_VERSION`) ;
4. attend que les services soient sains.

Un nouveau paquet SQL va dans `wizard-ui/backend/app/sql/schema/` et dans `PACKS` ; il doit pouvoir être
rejoué sans erreur, y compris après les paquets suivants.

**Retour arrière** : la fin de `make deploy` affiche les commandes pour relancer les images
`rollback-<date>`. Les paquets SQL ne se défont pas : ils ne font qu'ajouter.

## 5. Sauvegarde et restauration

```bash
make backup          # backups/<date>/borntoshare.sql.gz et borntoshare_logging.sql.gz
```

La sauvegarde **ne contient pas** `B2S_SECRET_MASTER_KEY` ni le `.env`. Conservez-les ailleurs, de manière
sûre : une base restaurée sans sa clé laisse tous les mots de passe stockés illisibles. Le tableau de bord
signale alors « mot de passe introuvable » pour chaque objet touché, et il faut les ressaisir.

Restauration : recharger les deux dumps dans une base vide (`gzip -dc … | mariadb …`), remettre le même
`.env` (même clé), puis `make up`. Détails dans [infrastructure.md](infrastructure.md).

## 6. Vérifier

```bash
make ps              # les quatre services « healthy » (le worker n'a pas de sonde : voir Infrastructure › Workers)
make logs-core-service
```

Dans l'application : Réglages avancés › Infrastructure (bases, file, workers, composants), et Suivi.
Tests de bout en bout sur un AD de test : [ad-lab.md](ad-lab.md).
