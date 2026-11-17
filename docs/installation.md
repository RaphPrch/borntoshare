# Installation et exploitation

## Prérequis

| Élément | Attendu |
|---|---|
| Hôte | Linux (RHEL 9 ou équivalent), `make`, `git` ; 2 vCPU, 4 Go de RAM au minimum. Selon la façon d'installer (section 2) : Podman 4+ et podman-compose ; ou Python 3.12, Redis, Node.js 22+, httpd et mod_ssl |
| Base | MariaDB 10.6+ ou 11.x, joignable en 3306 ; un compte avec les droits de création (root) le temps du wizard |
| Réseau | Les flux de [architecture.md](architecture.md#flux-à-ouvrir-vers-lextérieur) ouverts depuis l'hôte |
| Annuaire | Un AD joignable en LDAPS (636) et Kerberos (88) avec le certificat de son autorité ; un compte de lecture, un compte de connexion et, pour les accès, un compte délégué sur l'OU des groupes seulement (voir [droits-ad.md](droits-ad.md)) |
| Serveurs de fichiers | SMB 3 (445) et WinRM (5985, Kerberos) ; un compte administrateur local par serveur, sans droit dans l'AD (voir [droits-ad.md](droits-ad.md)) |
| Accès des utilisateurs | En conteneurs : un proxy inverse HTTPS devant le port 3000 ; `FRONTEND_PUBLIC_ORIGIN` = son URL. En hybride ou sans conteneur : httpd publié par l'installateur, avec votre certificat |

## 1. Le fichier `.env`

Un seul fichier à la racine du dépôt configure toute la pile. Il n'y a pas de mode « dev » ou « prod » : la pile se comporte toujours comme en production. Chaque conteneur ne reçoit que les variables
qu'il lit (`podman-compose.yml`).

```bash
cp .env.example .env     # facultatif : make wizard le fait s'il manque
chmod 600 .env
```

Il n'y a **rien à remplir** pour démarrer : ni mot de passe, ni jeton, ni clé. Le wizard complète les lignes de
l'installation (serveur MariaDB, façon d'installer, interface) ; les secrets sont générés par `make deploy`.

| Variable | Lue par | Valeur |
|---|---|---|
| `DB_HOST` | tous | Serveur MariaDB : la seule ligne requise pour la base (`DB_PORT` : 3306 par défaut) |
| `DB_TLS` | core, module 5S, `make deploy`, `make backup`, wizard | `off` (défaut) ou `on` : connexions à MariaDB chiffrées, certificat **et** nom du serveur vérifiés (autorité `capsule-runner/certs/db-ca.pem`, sinon celles du système). Écrit par le wizard (case « Connexion chiffrée ») |
| `DB_NAME`, `LOGGING_DB_NAME` | core-service | Facultatifs (`borntoshare`, `borntoshare_logging`) : bases des données et de l'audit, créées par le wizard |
| `DB_USER` | core-service | Facultatif (`b2s_core`) : compte SQL de l'application, lecture et écriture, créé par le wizard |
| `DB_MIGRATE_USER` | `make deploy`, `make backup` | Facultatif (`b2s_migrate`) : compte de migration, schéma et données, créé par le wizard |
| `FIVES_DB_NAME`, `FIVES_INVENTORY_DB_NAME`, `FIVES_DB_USER` | module 5S | Bases et compte du module (créés par le wizard quand la licence l'ouvre) |
| `FIVES_DB_HOST`, `FIVES_DB_PORT` | module 5S, `make deploy`, `make backup` | Vides (défaut) : les bases du 5S sont sur le serveur de `DB_HOST`. Renseignés : sur ce serveur à part (choisi dans le wizard, étape Modules) |
| `B2S_LAKE_URI`, `B2S_LAKE_S3_*` | fives-lake | Lac Parquet du module 5S (`file:///lake` ou `s3://bucket/préfixe`) : [module-5s.md](module-5s.md#lac-parquet) |
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
| `b2s_internal_token` | tous les services | Jeton partagé entre les services (en-tête `X-Internal-Token`). Généré par `make deploy` (48 caractères) ou repris de `INTERNAL_TOKEN` d'un ancien `.env` |
| `b2s_principal_key` | auth-service, frontend | Clé de signature du cookie de session. Générée par `make deploy` ou reprise de `PRINCIPAL_SIGNING_KEY` d'un ancien `.env` |
| `b2s_lake_s3_access`, `b2s_lake_s3_secret` | fives-lake | Clés du stockage S3 du lac Parquet, à créer à la main (`podman secret create`) ; `make deploy` les monte quand elles existent ([module-5s.md](module-5s.md#lac-parquet)) |

Chaque service lit un secret depuis son fichier (`NOM_FILE=/run/secrets/b2s_…`, `app/secret_files.py` pour les
services Python, `src/lib/server/secret-files.ts` pour l'interface) : la valeur n'est jamais dans l'environnement du
conteneur. **Mise à niveau** : une ligne `INTERNAL_TOKEN=` ou `PRINCIPAL_SIGNING_KEY=` encore dans `.env` est reprise
telle quelle dans son secret au `make deploy` suivant (les sessions en cours restent valides), puis retirée ; une
valeur d'exemple (« change-me… ») n'est jamais reprise : un secret neuf est généré.

Sans conteneur, les mêmes secrets sont des fichiers de `/etc/borntoshare/secrets` (0400, compte `b2s`) ; l'interface
sous httpd a sa copie des deux siens dans `/etc/borntoshare/web-secrets` (0440, compte `b2s-web`). `/etc/borntoshare`
lui-même est en 0755 root : chacun de ses contenus garde ses propres droits.

### Changer le jeton et la clé de session

```bash
make rotate-tokens                              # nouveau jeton des services : personne ne s'en aperçoit
make rotate-tokens WHICH=session CONFIRM=oui    # nouvelle clé de session : TOUT LE MONDE se reconnecte
make rotate-tokens WHICH=all CONFIRM=oui        # les deux
```

Le secret reçoit une valeur neuve, puis les services qui le lisent sont recréés (conteneurs) ou redémarrés
(systemd) ; l'interface sous httpd reçoit sa copie (même serveur) ou son paquet à nouveau (serveur annexe, par SSH ou
paquet à copier). À faire après le départ d'un administrateur qui a eu accès au serveur, ou en cas de doute. Un worker
installé sur un **autre serveur** partage le jeton : lui donner la nouvelle valeur (voir
[infrastructure.md](infrastructure.md#workers)).

Les certificats ne passent pas par une variable : on les dépose dans `capsule-runner/certs/`, monté en lecture
seule dans `/etc/b2s/certs` par auth-service, core-service, capsule-runner, le wizard et les conteneurs du 5S (sans
conteneur : copié dans `/etc/b2s/certs` par `make deploy`). Chaque fichier est pris en compte
s'il existe :

| Fichier | Lu par | Effet |
|---|---|---|
| `agent.crt` + `agent.key` | worker | Agent en HTTPS sur 8443 ; sans eux, HTTP sur 8080 (réseau interne uniquement) |
| `agent-ca.pem` | core-service | Autorité privée des certificats d'agent |
| `oidc-ca.pem` | auth-service | Autorité privée des serveurs Keycloak (SSO) |
| `syslog-ca.pem`, `splunk-ca.pem` | core-service | Autorité privée du collecteur syslog (TLS) ou du HEC Splunk (Settings › Extensions) |
| `opensearch-ca.pem`, `rabbitmq-ca.pem`, `minio-ca.pem`, `vault-ca.pem` | core-service | Autorité privée d'OpenSearch, RabbitMQ, MinIO (S3) ou Vault (Settings › Extensions) |
| `db-ca.pem` | core, module 5S, wizard, `make deploy`, `make backup` | Autorité privée des serveurs MariaDB (`DB_TLS=on`) |
| `lake-s3-ca.pem` | fives-lake | Autorité privée du stockage S3 du lac Parquet (HTTPS) |

`B2S_VERSION` n'est pas à renseigner : `make deploy` y met le commit et la date, affichés dans le menu du compte (en haut à droite).

## 2. L'installateur : trois façons d'installer

```bash
make wizard          # http://<hôte>:8080 (sans podman : le wizard tourne dans son propre environnement Python)
make wizard-check    # relire les prérequis du serveur, puis « Relire » dans l'installateur
```

`make wizard` lit d'abord ce que le serveur offre (`scripts/host-check.sh` → `secrets/.host-check.json` : podman,
Python, Node.js, httpd, mod_ssl, Redis, client MariaDB, SELinux, firewalld, sudo, disque, ports). L'installateur
s'ouvre sur le choix de la façon d'installer :

| Façon | Ce serveur | Interface web | Demande |
|---|---|---|---|
| **Tout en conteneurs** (recommandé) | Podman : services, Redis, interface | conteneur publié sur `FRONTEND_PUBLISHED_PORT`, ou derrière votre reverse proxy | podman, podman-compose |
| **Hybride** | Podman : services, Redis | service Node.js `b2s-web` publié par Apache httpd, **sur ce serveur ou sur un serveur web annexe** | en plus : httpd, mod_ssl, Node.js 22+ (là où tourne l'interface) |
| **Sans conteneur** | unités systemd `b2s-*`, chacune avec son environnement Python, Redis du système | idem hybride | Python 3.12+, Redis, client MariaDB, Node.js 22+, httpd, mod_ssl ; `sudo make deploy` |

Puis, étape par étape (seules celles qui servent à la façon choisie apparaissent) :

1. **Prérequis** : ce que le serveur offre pour cette façon ; un point rouge bloque, un orange se règle pendant le
   déploiement. En hybride et sans conteneur, on y choisit si l'interface est publiée ici ou sur un serveur annexe.
2. **Serveur MariaDB** : adresse et compte administrateur (root), testés ; utilisé pour cette installation seulement.
   « Connexion chiffrée (TLS) » : le test et toute l'installation passent en TLS vérifié, et `DB_TLS=on` est écrit
   (déposer avant l'autorité privée dans `capsule-runner/certs/db-ca.pem`).
3. **Bases et comptes SQL** : `DB_NAME`, `LOGGING_DB_NAME`, `DB_USER` (lecture et écriture), `DB_MIGRATE_USER`
   (schéma) ; mots de passe générés.
4. **Interface** : en conteneurs, l'adresse publique (`FRONTEND_PUBLIC_ORIGIN`) et le port publié ; sinon le nom
   d'hôte, le port HTTPS, le certificat et la clé (sur le serveur qui publie), avec l'aperçu du vhost écrit dans
   `/etc/httpd/conf.d/borntoshare.conf`.
5. **Réseau entre serveurs** (serveur annexe seulement) : le serveur annexe et son adresse IP, l'adresse de ce
   serveur vue de l'annexe, les ports de l'authentification, du core et du 5S (`B2S_AUTH_PORT` 8101,
   `B2S_CORE_PORT` 8102, `B2S_FIVES_PORT` 8105), publiés ici et ouverts **à l'adresse de l'annexe seulement**
   (firewalld). L'interface y est installée **par SSH** (clé `B2S_WEB_SSH_KEY`, compte `B2S_WEB_SSH_USER` avec sudo
   sans mot de passe sur l'annexe ; jamais de mot de passe) ou par un **paquet à copier**
   (`dist/borntoshare-web.tar.gz`, puis `sudo borntoshare-web/install-web.sh` sur l'annexe ; il contient le jeton des
   services : à transférer par un canal sûr, puis à supprimer). Le trafic entre les deux serveurs est en HTTP sur le
   réseau interne ; TLS entre eux : plus tard.
6. **Modules** : gouvernance des accès, 5S (clé de licence vérifiée hors ligne, ses deux bases et son compte ; au
   choix sur **un autre serveur MariaDB**, avec son propre compte administrateur testé : le compte de migration y est
   créé aussi, `FIVES_DB_HOST` et `FIVES_DB_PORT` sont écrits),
   **Messagerie (SMTP)** et **Journal syslog**. Ces deux derniers ajoutent chacun une étape, avec un envoi de test
   et « Passer, régler plus tard » (Réglages avancés › Notifications, › Extensions).
7. **Administrateur** : le premier compte local, mot de passe provisoire changé à la première connexion.
8. **Ce qui va être installé** : serveur par serveur.

**Étape 1, Préparer** (l'installateur) : bases et comptes, paquets SQL, administrateur, licence, modules, réglages
de messagerie et de syslog, vérification des droits. Une base déjà présente est conservée : rien n'est effacé.
Les réglages SMTP et syslog attendent le premier démarrage du core dans `secrets/.post-install.json`, le mot de
passe SMTP éventuel dans `secrets/.smtp-password` (0600) : le core les vérifie et les enregistre lui-même (son
coffre chiffre le mot de passe avec sa clé), puis les fichiers sont supprimés.

**Étape 2, Déployer** (automatique, `scripts/after-wizard.sh` sur le serveur) : l'installateur ajoute à `.env`
`B2S_DEPLOY_MODE` et les lignes de la façon choisie (aucun mot de passe), puis `make deploy` enchaîne ses phases,
suivies en direct par l'installateur : secrets, paquets SQL, point de retour, services, interface web (hybride et
sans conteneur), pare-feu (serveur annexe), messagerie et syslog, vérification. Une phase qui demande root sans
sudo dit la commande à lancer ; `make deploy` reprend ensuite tout, sans rien effacer.

| Façon | Où sont les secrets | Retour arrière |
|---|---|---|
| Conteneurs, hybride | secrets podman (`scripts/secrets.sh`) | images `rollback-<date>` (3 gardées par service) |
| Sans conteneur | `/etc/borntoshare/secrets` (0400, compte `b2s`) ; `<secret>.cnf` pour le client MariaDB (root) | `/opt/borntoshare/app/<service>.previous` |
| Interface sous httpd | `/etc/borntoshare/web.env` et `web.secrets` (0640 root:b2s-web) | `/opt/borntoshare/web.previous` |

Sans conteneur, l'agent du worker écoute sur `127.0.0.1:8180` (`B2S_AGENT_PORT`) : c'est l'adresse à déclarer dans
Infrastructure › Workers.

Le module 5S peut aussi être ajouté plus tard : relancer `make wizard` et coller la clé à l'étape « Modules » ; il
crée ses bases et son compte, puis déploie de lui-même.

## 3. Premier démarrage dans l'application

À la première connexion avec le compte administrateur, l'assistant `/setup` guide la déclaration de :
l'annuaire (LDAPS, certificat, compte de service), le premier serveur de fichiers (compte, partages trouvés),
les identités autorisées à se connecter et les administrateurs, puis les premiers dossiers gouvernés.

Ensuite, dans Administration › Settings : Réseau et DNS (serveurs DNS de chaque domaine), Infrastructure (workers,
planifications), Politique de nommage des groupes AD, Gouvernance (durées et motif
des demandes, groupes « ouverts à tous » de l'entreprise), Sessions (durées, échecs de connexion), Notifications
(serveur SMTP, e-mails envoyés, bandeau de maintenance : voir [notifications.md](notifications.md)), Extensions
(syslog, Splunk, Centreon).

## 4. Mises à jour

```bash
git pull
make deploy
```

`make deploy` (scripts/deploy.sh) :

1. applique les paquets SQL de `PACKS`, tous rejouables, puis les vues de `VIEWS` dont la définition a changé ;
2. étiquette les images en service `rollback-<date>` ;
3. reconstruit et recrée core, frontend, worker et auth, et le module 5S s'il est installé (en passant `B2S_VERSION`) ;
4. attend que les services soient sains.

Il refuse de redémarrer pendant un parcours du scanner 5S (`FORCE=1 make deploy` pour passer outre).

Un nouveau paquet SQL va dans `wizard-ui/backend/app/sql/schema/` et dans `PACKS` ; il doit pouvoir être
rejoué sans erreur, y compris après les paquets suivants.

**Retour arrière** : la fin de `make deploy` affiche les commandes pour relancer les images
`rollback-<date>`. Les paquets SQL ne se défont pas : ils ne font qu'ajouter.

## 5. Sauvegarde et restauration

```bash
make backup          # backups/<date>/<base>.sql.gz pour chaque base
```

La sauvegarde (avec le compte de migration ; les bases du module 5S aussi) **ne contient pas** la clé
`b2s_master_key` ni le `.env`. Conservez-les ailleurs, de manière sûre (`podman secret inspect --showsecret --format '{{.SecretData}}' b2s_master_key`) : une base restaurée sans sa clé laisse tous les mots de passe stockés illisibles. Le Dashboard
signale alors « mot de passe introuvable » pour chaque objet touché, et il faut les ressaisir.

Restauration : recharger les dumps par le compte de migration (les sauvegardes n'ont pas de `LOCK TABLES` depuis le
2026-11-17), remettre le même `.env` (même clé), puis `make deploy`. Commandes dans
[infrastructure.md](infrastructure.md#secrets-et-sauvegarde).

## 6. Vérifier

```bash
make ps              # tous les services « healthy » : /health vérifie la base et Redis (core), Redis (auth),
                     # Redis et les processus Dramatiq (worker) ; un service « unhealthy » dit pourquoi dans /health
make logs-core-service
```

Dans l'application : Settings › Infrastructure (bases, file, workers, composants), et Governance Jobs.
Tests de bout en bout sur un AD de test : [ad-lab.md](ad-lab.md).
