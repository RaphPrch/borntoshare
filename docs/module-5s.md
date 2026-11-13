# Module 5S (rangement des partages)

Module sous licence (activé par le wizard, étape « Licence et modules ») : il mesure les dossiers gouvernés sur
leurs serveurs de fichiers et note leur tenue selon les **5S** (Trier, Ranger, Nettoyer, Standardiser, Maintenir).
Menu **5S** de l'application.

Le code du module (`fives-service`, `fives-scanner`, ses paquets SQL `wizard-ui/backend/app/sql/fives*`) est
développé dans un dépôt à part et n'est pas versionné ici ; ses écrans le sont (`frontend-service/src/routes/(app)/five-s`).

| Conteneur | Rôle |
|---|---|
| fives-service | API du module (`/modules/fives/*` derrière le BFF) : arborescence, doublons, quarantaine, scores |
| fives-scanner | Parcourt les dossiers **sur** leur serveur Windows (WinRM 5985, Kerberos, sans agent), un parcours complet planifié et des passages incrémentaux ; plusieurs instances possibles (une par site) |

Bases : `b2s_fives` (résultats, décisions, quarantaine, historique des scores) et `b2s_fives_inventory`
(empreintes), avec le compte SQL `b2s_fives` (lecture et écriture, jamais le schéma).

## Écrans

| Écran | Contenu |
|---|---|
| 5S des partages (`/five-s`) | score de chaque dossier sur 100, par pilier ; « Quoi faire d'abord » : les actions qui relèvent le plus de dossiers |
| Explorateur (`/five-s/explore/<dossier>`) | arborescence à gauche, contenu au centre (dates, ancienneté, droits, doublons), fiche du sous-dossier : historique, ACL, chaîne d'héritage, actions ; atelier des 5 piliers avec la tendance des scores |
| Doublons (`/five-s/duplicates/<dossier>`) | groupes de fichiers identiques (empreinte), filtre par sous-dossier, décision par groupe |
| Rapport (`/five-s/report/<dossier>`) | volumes, âges, types, et les trois mesures précédentes, rétablissables |
| Scanner (`/five-s/scanner`) | file et parcours en cours, réglages (fréquence, parcours complet, scans simultanés par serveur, empreintes par morceau) |

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
