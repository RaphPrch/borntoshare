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
| `DB_HOST` | tous | Serveur MariaDB : la seule ligne requise pour la base (`DB_PORT` : 3306 par défaut) |
| `DB_NAME`, `LOGGING_DB_NAME` | core-service | Facultatifs (`borntoshare`, `borntoshare_logging`) : bases des données et de l'audit, créées par le wizard |
| `DB_USER` | core-service | Facultatif (`b2s_core`) : compte SQL de l'application, lecture et écriture, créé par le wizard |
| `DB_MIGRATE_USER` | `make deploy`, `make backup` | Facultatif (`b2s_migrate`) : compte de migration, schéma et données, créé par le wizard |
| `FIVES_DB_NAME`, `FIVES_INVENTORY_DB_NAME`, `FIVES_DB_USER` | module 5S | Bases et compte du module (créés par le wizard quand la licence l'ouvre) |
| `FRONTEND_PUBLIC_ORIGIN` | frontend | URL publique exacte (schéma, hôte, port) : sert de contrôle d'origine |
| `FRONTEND_PUBLISHED_PORT` | compose | Port publié sur l'hôte (3000) |
| `RUNNER_MAX_SCOPE` | worker | `write` (normal) ou `read` (worker de lecture seule) |
| `WIZARD_PORT` | wizard | Port du wizard |

**Aucun mot de passe dans `.env`.** Les mots de passe et les clés sont des secrets podman, montés en fichiers
(`/run/secrets`, mode 0400, à l'UID du service) dans les seuls conteneurs qui les lisent ; ils n'apparaissent ni
dans `.env` ni dans `podman inspect`. `make deploy` (`scripts/secrets.sh`) les crée :

| Secret | Lu par | Origine |
|---|---|---|
| `b2s_db_core`, `b2s_db_migrate`, `b2s_db_fives` | core ; `make deploy` et `make backup` ; module 5S | Générés par le wizard, écrits dans `secrets/` (0600), importés puis supprimés par `make deploy` |
| `b2s_redis` | redis, auth, core, worker | Généré par `make deploy` (ou repris de `REDIS_PASSWORD` d'un ancien `.env`) |
| `b2s_master_key` | core-service | Généré par `make deploy` (ou repris de `B2S_SECRET_MASTER_KEY`) : chiffre les mots de passe stockés. **À sauvegarder à part** |

Générer un secret : `openssl rand -base64 48 | tr -d '/+=' | cut -c1-48`.

Les certificats ne passent pas par une variable : on les dépose dans `capsule-runner/certs/`, monté en lecture
seule dans `/etc/b2s/certs` par auth-service, core-service et capsule-runner. Chaque fichier est pris en compte
s'il existe :

| Fichier | Lu par | Effet |
|---|---|---|
| `agent.crt` + `agent.key` | worker | Agent en HTTPS sur 8443 ; sans eux, HTTP sur 8080 (réseau interne uniquement) |
| `agent-ca.pem` | core-service | Autorité privée des certificats d'agent |
| `oidc-ca.pem` | auth-service | Autorité privée des serveurs Keycloak (SSO) |
| `syslog-ca.pem`, `splunk-ca.pem` | core-service | Autorité privée du collecteur syslog (TLS) ou du HEC Splunk (Réglages avancés › Extensions) |

`B2S_VERSION` n'est pas à renseigner : `make deploy` y met le commit et la date, affichés en bas du menu.

## 2. Le wizard : bases, administrateur et licence

```bash
make wizard          # http://<hôte>:8080
```

Le wizard part des noms déjà dans `.env` ; seul le mot de passe de l'administrateur MariaDB s'y saisit. Il demande :

1. **Serveur MariaDB** : adresse et compte administrateur (root), testés ; utilisé pour cette installation seulement.
2. **Bases BornToShare** : base des données (`DB_NAME`), base du journal d'audit (`LOGGING_DB_NAME`), le compte
   de l'application (`DB_USER` : lecture et écriture) et celui des migrations (`DB_MIGRATE_USER` : schéma), dont
   les mots de passe sont générés.
3. **Administrateur** : identifiant et mot de passe du premier compte local administrateur.
4. **Licence et modules** (facultatif) : la clé de licence, vérifiée hors ligne. Si elle ouvre le module 5S : ses deux
   bases (`FIVES_DB_NAME`, `FIVES_INVENTORY_DB_NAME`) et son propre compte (`FIVES_DB_USER` : lecture et écriture).
5. **Installation** : récapitulatif, puis chaque action (bases et comptes, paquets SQL, administrateur, licence,
   module, vérification des comptes) avec son résultat.

Une base déjà présente est conservée : rien n'est effacé, les paquets SQL s'appliquent à nouveau.

**La suite est automatique** (`scripts/after-wizard.sh`, lancé par `make wizard` sur le serveur) : une fois
l'installation réussie, il ajoute à `.env` les lignes du wizard (l'adresse du serveur, et les noms qui diffèrent de
ceux par défaut), lance `make deploy` (secrets podman, paquets SQL, images, services) puis arrête le wizard.
Le dernier écran du wizard suit ce déploiement et donne le lien vers BornToShare. En cas d'échec, il montre la fin
du journal : corriger, puis `make deploy`.

Le module 5S peut aussi être ajouté plus tard : relancer `make wizard` et coller la clé à l'étape « Licence et
modules » ; il crée ses bases et son compte, puis déploie de lui-même.

## 3. Premier démarrage dans l'application

À la première connexion avec le compte administrateur, l'assistant `/setup` guide la déclaration de :
l'annuaire (LDAPS, certificat, compte de service), le premier serveur de fichiers (compte, partages trouvés),
les identités autorisées à se connecter et les administrateurs, puis les premiers dossiers gouvernés.

Ensuite, dans Réglages avancés : Réseau et DNS (serveurs DNS de chaque domaine), Infrastructure (workers,
planifications), Politique de nommage des groupes AD, Gouvernance (nombre minimal de gardiens, durées et motif
des demandes, groupes « ouverts à tous » de l'entreprise), Sessions (durées, échecs de connexion), Notifications
(serveur SMTP, e-mails envoyés, bandeau de maintenance), Extensions (syslog, Splunk, Centreon).

## 4. Mises à jour

```bash
git pull
make deploy
```

`make deploy` (scripts/deploy.sh) :

1. applique les paquets SQL de `PACKS`, tous rejouables, puis les vues de `VIEWS` dont la définition a changé ;
2. étiquette les images en service `rollback-<date>` ;
3. reconstruit et recrée core, frontend, worker et auth (en passant `B2S_VERSION`) ;
4. attend que les services soient sains.

Un nouveau paquet SQL va dans `wizard-ui/backend/app/sql/schema/` et dans `PACKS` ; il doit pouvoir être
rejoué sans erreur, y compris après les paquets suivants.

**Retour arrière** : la fin de `make deploy` affiche les commandes pour relancer les images
`rollback-<date>`. Les paquets SQL ne se défont pas : ils ne font qu'ajouter.

## 5. Sauvegarde et restauration

```bash
make backup          # backups/<date>/<base>.sql.gz pour chaque base
```

La sauvegarde (avec le compte de migration ; les bases du module 5S aussi) **ne contient pas** la clé
`b2s_master_key` ni le `.env`. Conservez-les ailleurs, de manière sûre (`podman secret inspect --showsecret --format '{{.SecretData}}' b2s_master_key`) : une base restaurée sans sa clé laisse tous les mots de passe stockés illisibles. Le tableau de bord
signale alors « mot de passe introuvable » pour chaque objet touché, et il faut les ressaisir.

Restauration : recharger les deux dumps dans une base vide (`gzip -dc … | mariadb …`), remettre le même
`.env` (même clé), puis `make up`. Détails dans [infrastructure.md](infrastructure.md).

## 6. Vérifier

```bash
make ps              # tous les services « healthy » : /health vérifie la base et Redis (core), Redis (auth),
                     # Redis et les processus Dramatiq (worker) ; un service « unhealthy » dit pourquoi dans /health
make logs-core-service
```

Dans l'application : Réglages avancés › Infrastructure (bases, file, workers, composants), et Suivi.
Tests de bout en bout sur un AD de test : [ad-lab.md](ad-lab.md).
