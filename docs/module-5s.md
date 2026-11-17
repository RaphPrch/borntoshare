# Module 5S (rangement des partages)

Module sous licence (activé par le wizard, étape « Licence et modules ») : il mesure les dossiers gouvernés sur
leurs serveurs de fichiers et note leur tenue selon les **5S** (Trier, Ranger, Nettoyer, Standardiser, Maintenir).
Ses écrans forment la section **Storage Intelligence** du menu (administrateurs et gardiens).

Le code du module (`fives-service`, `fives-scanner`, ses paquets SQL `wizard-ui/backend/app/sql/fives*`) est
livré sous licence dans un **dépôt privé à part** (`b2s-fives-module`) et n'est pas versionné ici : ces chemins sont
dans `.gitignore`. Ses écrans, eux, sont versionnés ici (`frontend-service/src/routes/(app)/five-s`) ; sans le
module, ils n'apparaissent pas dans le menu.

## Installer le module

1. Récupérer le dépôt du module (accès fourni avec la licence) à côté de celui-ci.
2. Copier `fives-service/` et `fives-scanner/` à la racine de ce dépôt, et `wizard-sql/fives/`,
   `wizard-sql/fives_inventory/` dans `wizard-ui/backend/app/sql/`.
3. `make wizard`, étape « Licence et modules » : clé de licence, puis les noms des deux bases et du compte SQL.
   Le wizard crée les bases, le compte `b2s_fives` et son secret `b2s_db_fives`. Les deux bases peuvent aller sur
   **un autre serveur MariaDB** (case « Ses deux bases sur un autre serveur MariaDB », avec le compte
   administrateur de ce serveur, testé) : l'inventaire grossit avec le nombre de fichiers sans peser sur la
   gouvernance. Le wizard y crée aussi le compte de migration et écrit `FIVES_DB_HOST` / `FIVES_DB_PORT`.
4. `make deploy` démarre `fives-service` et `fives-scanner` dès que ce secret existe (profil `fives`).

Mise à jour du module : recopier les dossiers depuis son dépôt, puis `make deploy` (les paquets SQL du module
sont appliqués à chaque déploiement). `fives-scanner` se construit depuis la racine de ce dépôt : il reprend le
code WinRM de `capsule-runner`.

| Conteneur | Rôle |
|---|---|
| fives-service | API du module (`/modules/fives/*` derrière le BFF) : arborescence, doublons, quarantaine, scores |
| fives-scanner | Parcourt les dossiers **sur** leur serveur Windows (WinRM 5985, Kerberos, sans agent), un parcours complet planifié et des passages incrémentaux ; plusieurs instances possibles (`FIVES_SCANNERS` dans `.env` ; en le baissant, `make deploy` retire les instances en trop) |
| fives-lake | Lac Parquet : export quotidien de l'historique (voir plus bas), quand `B2S_LAKE_URI` est dans `.env` |

Bases : `b2s_fives` (résultats, décisions, quarantaine, historique des scores) et `b2s_fives_inventory`
(empreintes), avec le compte SQL `b2s_fives` (lecture et écriture, jamais le schéma).

## Écrans

| Menu Storage Intelligence | Contenu |
|---|---|
| Explorer (`/five-s/explore`) | à gauche, l'**arborescence** du parc (zones › serveurs › dossiers mesurés, puis les sous-dossiers du dossier ouvert), toujours présente ; à droite, le **tableau** de la portée choisie : volume et courbe des dernières mesures, place prise par les doublons, fichiers sensibles, dernière mesure, score ; filtres (score sous 60, fichiers sensibles, doublons, en croissance, pas mesuré depuis 30 jours), tri, sélection (mesurer, analyser la sensibilité, exporter). Recherche de fichiers dans tous les dossiers mesurés : un résultat ouvre son dossier avec le fichier choisi |
| Contenu et Atelier 5S (`/five-s/explore/<dossier>`) | fiche d'un dossier en onglets (Contenu, Atelier 5S, Doublons, Droits à revoir, Rapport) ; ses sous-dossiers dans l'arborescence de gauche, le contenu au centre (dates, ancienneté, droits, doublons) ; à droite la fiche du sous-dossier (historique, ACL, chaîne d'héritage, actions) ou, au clic sur un fichier, la **fiche du fichier** (pourquoi il est signalé, ses copies, qui peut l'ouvrir) ; atelier des 5 piliers avec la tendance des scores. Juste après une première mesure, la page suit le scanner et affiche l'arborescence dès qu'elle arrive |
| Droits à revoir (`/five-s/access/<dossier>`) | tous les sous-dossiers à regarder : SID orphelin, écriture pour toute l'entreprise, contrôle total, droits posés à la main, héritage rompu ; « qui y a accès et pourquoi » pour celui qu'on choisit |
| Doublons (`/five-s/duplicates/<dossier>`) | groupes de fichiers identiques (empreinte), filtre par sous-dossier, décision par groupe |
| Inventory (`/five-s/scanner`) | bandeau du scanner, puis trois onglets : **Scans** (file et parcours en cours), **Dossiers** (inventaire par dossier, mesure des jamais mesurés, clic droit : fiche, explorer, mesurer, annuler), **Quarantaine** (copies et dossiers archivés de tous les dossiers, filtres, restauration, durée de purge), **Réglages** (administrateurs : fréquence, parcours complet, scans simultanés par serveur, empreintes par morceau, propriétaires des fichiers, purge) |
| Analytics (`/five-s`) | score de chaque dossier sur 100, par pilier, sur tout le parc ou une branche de l'arborescence ; « Quoi faire d'abord » : les actions qui relèvent le plus de dossiers |
| Rapport (`/five-s/report/<dossier>`), avec « Depuis la mesure précédente » : dossiers apparus et disparus, ceux qui ont grossi ou diminué, droits et héritage modifiés | volumes, âges, types, et les trois mesures précédentes, rétablissables |

Dans l'Explorer, chaque fichier montre sa taille, sa création, sa dernière modification, son dernier accès
(indicatif), son extension, son propriétaire NTFS si l'administrateur l'a demandé (Inventory › Réglages : une
lecture de plus par fichier, désactivée par défaut) et la marque « Sensible » quand l'analyse de sensibilité du
Core l'a relevé. La fiche d'un sous-dossier dit **qui y a accès et pourquoi** : chaque entrée de ses droits est
résolue par le Core avec son annuaire (groupe et ses membres, groupes imbriqués compris ; compte ; comptes système ;
« tout le monde » ; SID orphelin ; compte inconnu), puis les personnes avec leur niveau et chaque chemin qui y mène,
les droits excessifs (écriture pour toute l'entreprise, contrôle total hors administrateurs, compte ajouté à la main,
SID orphelin, refus) et ce que le dossier change par rapport à son parent. Le module ne garde aucune identité : il
envoie les droits lus au Core (`POST /internal/modules/fives/folder-access`).

La fiche d'un dossier (Governance › Storage Roots) résume aussi le module dans son onglet **Stockage · 5S**, et
Pilot répond aux questions de volume (dossiers jamais mesurés, données froides, doublons, quotas).

## Actions

Réservées aux **administrateurs** et aux **gardiens du dossier** (vérifié par fives-service auprès du Core, quelle
que soit l'interface), et seulement **sous** le dossier gouverné : jamais le dossier lui-même, un dossier voisin du
même partage, ni les dossiers `_B2S_Quarantaine` et `_B2S_Archives`. Chaque demande et chaque résultat est inscrit
au **journal d'audit chaîné du Core** ; si le journal ne peut pas l'enregistrer, rien n'est fait.

| Action | Effet | Garde-fous |
|---|---|---|
| Écarter des doublons | les copies vont en **quarantaine** (`_B2S_Quarantaine\<date>\…` sur le même partage) | juste avant le déplacement, sur le serveur : SHA-256 **complet** de la copie et de la copie gardée, comparés ; taille et date de modification égales à celles de la mesure ; vérifiée de nouveau une fois déplacée (remise en place si elle a changé) ; confirmation au-delà de 50 Go ; rien n'est écrasé |
| Restaurer | la copie ou le dossier revient à sa place | refusé si quelque chose occupe la place ; signale une copie modifiée en quarantaine |
| Purger la quarantaine | suppression définitive des copies | **désactivée par défaut** ; un administrateur choisit un délai (Inventory › Réglages) ; empreinte vérifiée avant suppression |
| Archiver un dossier | il part dans `_B2S_Archives\<date>\<chemin>` | jamais purgé ; restaurable |
| Rétablir l'héritage d'un sous-dossier | réactive l'héritage NTFS et retire les entrées en double | administrateurs ; chemin limité à l'intérieur du dossier gouverné |

Les chemins sont contrôlés deux fois : par fives-service (chemin relatif au partage, sans `..`, `:` ni caractère
générique) et par le script PowerShell, sur les chemins complets résolus, avant tout déplacement ou suppression.

## Fiabilité des mesures

- **Complète, partielle ou échantillonnée** : chaque mesure le dit, avec ses raisons et les dossiers concernés
  (Explorer, Inventory, fiche du dossier). Partielle : liste de fichiers coupée (300 000 par morceau), plus de
  50 000 dossiers ou ACL dans un morceau, dossiers illisibles, droits illisibles, morceau illisible (sa mesure
  précédente est gardée). Échantillonnée : doublons cherchés sur une partie des fichiers de même taille
  (`hash_files_max`) ou empreintes encore en cours. Les doublons **entre** dossiers sont toujours une estimation
  (plus gros fichiers de chaque dossier).
- Les droits sont lus en SID : un compte supprimé de l'annuaire reste visible comme SID orphelin, au lieu de faire
  disparaître tous les droits du dossier ; au plus 64 entrées gardées par dossier, le total est indiqué.
- Les dossiers vides ont leur ligne dans l'arborescence.
- Le dernier accès est indicatif : Windows le met à jour en différé, ou pas du tout s'il est désactivé.
- Un seul calcul du score 5S (fives-service) : la tendance de l'atelier enregistre, après chaque mesure, le même
  score que la page Analytics. Les anciens points (calcul du scanner, avant 11/2026) sont gardés mais pas mélangés.
- Une mesure vide ne remplace jamais une mesure pleine : le dossier passe en alerte « dossier illisible » et garde
  ses chiffres (`fives_unreadable:<dossier>`).
- Les trois mesures précédentes sont gardées, et rétablissables depuis le Rapport.
- Un parcours interrompu par un redémarrage reprend au démarrage du scanner ; les appels vers core-service sont
  relancés (2, 5, 15, 30, 60 s).
- `make deploy` refuse de redémarrer le module pendant un parcours (`FORCE=1` pour passer outre).
- Schéma : fives-service et fives-scanner vérifient toutes les tables et colonnes des paquets SQL du module. Tant
  qu'il en manque, le service répond 503 `SCHEMA_NOT_READY` (l'écran Settings › Fonctionnalités dit lesquelles) et
  le scanner ne prend ni scan ni déplacement.

Le compte du serveur de fichiers doit pouvoir ouvrir une session WinRM en Kerberos et lire tout le dossier : voir
[droits-ad.md](droits-ad.md#le-compte-du-serveur-de-fichiers).

Connexions à MariaDB : `DB_TLS=on` vaut aussi pour le module (certificat et nom du serveur vérifiés, voir
[securite.md](securite.md#connexions-à-mariadb)).

## Lac Parquet

L'historique des inventaires (snapshots quotidiens vérifiés, publiés atomiquement) est écrit par `fives-lake`, un
processus à part de l'API. Fonctionnement détaillé : `docs/lake.md` du dépôt du module.

| Où | `.env` | Installation |
|---|---|---|
| Volume local (`b2s-lake`) | `B2S_LAKE_URI=file:///lake` | rien d'autre ; sans conteneur : `/var/lib/borntoshare/lake` |
| Répertoire monté (disque dédié, NFS, SMB) | `B2S_LAKE_URI=file:///lake` | le volume `b2s-lake` attaché au répertoire : `podman volume create --opt type=none --opt o=bind --opt device=/srv/b2s-lake b2s-lake` (répertoire à l'UID 10005 du conteneur, soit 110004 sur l'hôte en podman sans root) |
| Stockage S3 compatible (MinIO, Ceph…) | `B2S_LAKE_URI=s3://bucket/préfixe`, `B2S_LAKE_S3_ENDPOINT=https://…`, `B2S_LAKE_S3_REGION` | les clés en secrets podman `b2s_lake_s3_access` et `b2s_lake_s3_secret` (jamais dans `.env`) ; autorité privée : `capsule-runner/certs/lake-s3-ca.pem` |

```bash
# Clés S3 : tapées, jamais affichées ni dans l'historique
read -rs -p "Access key : " K; echo; printf '%s' "$K" | podman secret create b2s_lake_s3_access -; unset K
read -rs -p "Secret key : " K; echo; printf '%s' "$K" | podman secret create b2s_lake_s3_secret -; unset K
make deploy        # monte les deux secrets dans fives-lake (podman-compose.lake-s3.yml) dès qu'ils existent
podman exec fives-lake python -m app.lake export && podman exec fives-lake python -m app.lake verify --all
```

Sans conteneur, les clés sont les fichiers `/etc/borntoshare/secrets/b2s_lake_s3_access` et `…_secret` (0400,
compte `b2s`), et le lac tourne dans l'unité `b2s-lake`.
