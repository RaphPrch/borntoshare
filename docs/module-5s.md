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
   Le wizard crée les bases, le compte `b2s_fives` et son secret `b2s_db_fives`.
4. `make deploy` démarre `fives-service` et `fives-scanner` dès que ce secret existe (profil `fives`).

Mise à jour du module : recopier les dossiers depuis son dépôt, puis `make deploy` (les paquets SQL du module
sont appliqués à chaque déploiement). `fives-scanner` se construit depuis la racine de ce dépôt : il reprend le
code WinRM de `capsule-runner`.

| Conteneur | Rôle |
|---|---|
| fives-service | API du module (`/modules/fives/*` derrière le BFF) : arborescence, doublons, quarantaine, scores |
| fives-scanner | Parcourt les dossiers **sur** leur serveur Windows (WinRM 5985, Kerberos, sans agent), un parcours complet planifié et des passages incrémentaux ; plusieurs instances possibles (une par site) |

Bases : `b2s_fives` (résultats, décisions, quarantaine, historique des scores) et `b2s_fives_inventory`
(empreintes), avec le compte SQL `b2s_fives` (lecture et écriture, jamais le schéma).

## Écrans

| Menu Storage Intelligence | Contenu |
|---|---|
| Explorer (`/five-s/explore`, puis `/five-s/explore/<dossier>`) | choix du dossier, puis arborescence à gauche, contenu au centre (dates, ancienneté, droits, doublons), fiche du sous-dossier : historique, ACL, chaîne d'héritage, actions ; atelier des 5 piliers avec la tendance des scores. Juste après une première mesure, la page suit le scanner et affiche l'arborescence dès qu'elle arrive |
| Doublons (`/five-s/duplicates/<dossier>`, depuis Explorer) | groupes de fichiers identiques (empreinte), filtre par sous-dossier, décision par groupe |
| Inventory (`/five-s/scanner`) | bandeau du scanner, puis trois onglets : **Scans** (file et parcours en cours), **Dossiers** (inventaire par dossier, mesure des jamais mesurés, clic droit : fiche, explorer, mesurer, annuler), **Réglages** (administrateurs : fréquence, parcours complet, scans simultanés par serveur, empreintes par morceau) |
| Analytics (`/five-s`) | score de chaque dossier sur 100, par pilier, sur tout le parc ou une branche de l'arborescence ; « Quoi faire d'abord » : les actions qui relèvent le plus de dossiers |
| Rapport (`/five-s/report/<dossier>`, depuis Analytics) | volumes, âges, types, et les trois mesures précédentes, rétablissables |

La fiche d'un dossier (Governance › Storage Roots) résume aussi le module dans son onglet **Stockage · 5S**, et
Pilot répond aux questions de volume (dossiers jamais mesurés, données froides, doublons, quotas).

## Actions

| Action | Effet | Garde-fous |
|---|---|---|
| Écarter des doublons | les copies vont en **quarantaine** (`_B2S_Quarantaine\<date>\…` sur le même partage) | confirmation au-delà de 50 Go ; restauration possible ; purge à 30 jours |
| Archiver un dossier | il part dans `_B2S_Archives\<date>\<chemin>` | jamais purgé ; restaurable |
| Rétablir l'héritage d'un sous-dossier | réactive l'héritage NTFS et retire les entrées en double | administrateurs ; chemin limité à l'intérieur du dossier gouverné |

## Fiabilité des mesures

- Une mesure vide ne remplace jamais une mesure pleine : le dossier passe en alerte « dossier illisible » et garde
  ses chiffres (`fives_unreadable:<dossier>`).
- Les trois mesures précédentes sont gardées, et rétablissables depuis le Rapport.
- Un parcours interrompu par un redémarrage reprend au démarrage du scanner ; les appels vers core-service sont
  relancés (2, 5, 15, 30, 60 s).
- `make deploy` refuse de redémarrer le module pendant un parcours (`FORCE=1` pour passer outre).

Le compte du serveur de fichiers doit pouvoir ouvrir une session WinRM en Kerberos et lire tout le dossier : voir
[droits-ad.md](droits-ad.md#le-compte-du-serveur-de-fichiers).
