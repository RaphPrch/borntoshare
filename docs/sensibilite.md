# Sensibilité et exposition des dossiers

Deux vues répondent à la même question, « qui peut lire quoi » :

- la **sensibilité** d'un dossier : les fichiers qui contiennent des secrets ou des données personnelles, et qui
  peut les ouvrir ;
- la **carte d'exposition** (`/exposure`) : jusqu'où chaque dossier gouverné est ouvert, d'après la dernière lecture
  de ses droits sur le serveur.

## Scan de sensibilité

Lancé depuis la fiche d'un dossier (bloc « Sensibilité ›  Scanner le dossier »), ou par une politique. Le worker
(action `scan_smb_sensitivity`) lit le dossier avec le compte du serveur de fichiers :

1. **les noms** de tous les fichiers, à chaque scan (peu coûteux) ;
2. **le contenu** des petits fichiers texte (1 Mo au plus) modifiés depuis le scan précédent, 1 000 fichiers et
   50 Mo au plus par passage ; un gros dossier se lit en plusieurs passages, qui s'enchaînent tout seuls ;
3. **les droits** de chaque fichier signalé (`smbcacls`, 100 fichiers et 90 secondes au plus par passage).

Sur un serveur Windows, la liste des fichiers vient de WinRM (Kerberos), bien plus rapide ; sinon de SMB.

| Catégorie | Exemples |
|---|---|
| Mot de passe | `password=…` dans un `web.config`, un script, un fichier texte |
| Fichier ou coffre de mots de passe | `mots de passe.xlsx`, `*.kdbx`, export KeePass |
| Clé privée, clé ou jeton d'API | `id_rsa`, `-----BEGIN … PRIVATE KEY-----`, clés cloud |
| Données personnelles, bancaires | numéros vérifiés par leur clé (NIR, IBAN, carte) |
| Fichier à risque | sauvegarde de base, boîte aux lettres, exécutable ou installeur |

Seuls le chemin, la règle, la ligne et un **extrait masqué** sont gardés : le secret lui-même n'est jamais stocké.
Un fichier peut être marqué « faux positif » avec une raison ; il ne compte plus et reste listé à part.

## Qui peut ouvrir les fichiers signalés

Chaque fichier signalé porte ses droits : comptes, niveau (lecture, modification, contrôle total), hérités ou non,
propriétaire, et « droits propres » quand le fichier ne suit plus l'héritage de son dossier.

Un fichier est **ouvert à tous** quand une entrée autorise la lecture à :
- `Tout le monde` / `Everyone`, `Utilisateurs authentifiés`, `BUILTIN\Utilisateurs`, `Utilisateurs du domaine` ;
- ou un **grand groupe** de l'annuaire : au moins 20 % des comptes, et 25 membres au minimum (par exemple
  `GG_Tous`). Le groupe en cause est nommé.

Le bloc Sensibilité regroupe les fichiers par **cause** : le dossier commun, les comptes qui l'ouvrent, et si le
droit est hérité (posé sur ce dossier ou au-dessus) ou posé sur les fichiers. Il n'y a souvent qu'une cause : un
dossier qui donne la lecture à tout le monde.

## L'alerte « fichiers sensibles ouverts à tous »

Quand des fichiers de mots de passe, de clés ou de données personnelles ou bancaires sont ouverts à tous, une alerte
de gouvernance (gravité haute, `sensitive_open:<dossier>`) s'ouvre, et les gardiens reçoivent un e-mail à son
ouverture (voir [notifications.md](notifications.md)). Les fichiers à risque (installeurs…) ne la déclenchent pas.
Elle se ferme d'elle-même au scan qui voit les droits restreints, ou quand les fichiers sont marqués faux positifs.

Corriger : déplacer les fichiers dans un dossier réservé à l'équipe, ou retirer l'entrée large du dossier en cause.

## Carte d'exposition

Chaque dossier gouverné est classé d'après la dernière lecture de son ACL : ouvert à tous en modification, ouvert
à tous en lecture, comptes posés hors de BornToShare, gouverné (seulement ses groupes AD et les comptes système
attendus), ou pas encore lu. Réglages avancés › Gouvernance complète les deux listes intégrées :
- les **groupes ouverts à tous** de l'entreprise (ex. `CORP\GG_Tous`) ;
- les **comptes d'administration attendus** : un Administrateur renommé par un durcissement CIS (ex. `CORP\sla-prd`)
  n'est alors plus signalé comme « compte hors BornToShare ».
