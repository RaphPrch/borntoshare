# Droits minimums dans l'Active Directory et sur les serveurs

BornToShare utilise un compte par usage, avec le moindre privilège. Aucun compte n'est administrateur du domaine.
Un seul compte écrit dans l'AD (`svc-b2s-prov`), et uniquement dans l'OU des groupes d'accès. Cette page dit ce que
chaque compte doit avoir, ce qu'il ne doit pas avoir, comment le poser et comment le vérifier.

Les noms (`svc-b2s-*`, `CORP`, `OU=B2S Groups`) sont ceux du laboratoire `CORP.LOCAL` : à adapter.

## Les comptes

| Compte | Réglé dans BornToShare | Sert à | Droits nécessaires |
|---|---|---|---|
| `svc-b2s-sync` | Annuaire › compte principal et compte « snapshot » | Instantanés (utilisateurs, groupes, appartenances), recherche de personnes, contrôle de santé de l'annuaire, lecture des espaces de noms DFS | **Aucun droit ajouté** : la lecture accordée par défaut aux utilisateurs authentifiés suffit |
| `svc-b2s-auth` | Annuaire › compte « auth » | Retrouver l'utilisateur qui se connecte, avant que l'AD vérifie son mot de passe | **Aucun droit ajouté** |
| `svc-b2s-prov` | Annuaire › compte « provisioning » | Créer les groupes d'accès, ajouter et retirer leurs membres | Délégation sur l'OU des groupes, détaillée ci-dessous |
| Compte du serveur de fichiers (ex. `userfiler01`) | Serveurs › compte du serveur | Partages, ACL NTFS, mesures et sensibilité, quotas FSRM, WinRM | Administrateur local du serveur de fichiers ; **aucun droit dans l'AD** |

Les trois comptes `svc-b2s-*` vivent dans une OU à part (`OU=Comptes de service,OU=CORP`) et n'appartiennent à
aucun groupe. Le compte du serveur de fichiers peut être membre d'un groupe de tier (ici `T1-Comptes`), qui lui
donne l'accès d'administration aux serveurs membres.

Pour tous ces comptes :
- cocher **« Le compte est sensible et ne peut pas être délégué »** : BornToShare ne fait jamais de délégation Kerberos ;
- aucun SPN, aucune délégation contrainte (`msDS-AllowedToDelegateTo` vide) ;
- mot de passe long et aléatoire, saisi une seule fois dans l'interface (il est chiffré dans le coffre de BornToShare).

## La délégation de `svc-b2s-prov`

BornToShare n'écrit que trois choses dans l'AD : il **crée** un groupe global de sécurité (attributs
`sAMAccountName`, `groupType`, `description`, `info` posés à la création), il **ajoute** et il **retire** des valeurs
de son attribut `member`. Il ne supprime jamais de groupe et ne modifie aucun autre attribut. La délégation se
limite donc à :

| Objet | Droit | Portée |
|---|---|---|
| `OU=B2S Groups,OU=CORP` | Créer des objets **groupe** (`CreateChild`, classe `group`) | Cet objet seulement |
| `OU=B2S Groups,OU=CORP` | Écrire l'attribut **`member`** (`WriteProperty`, attribut `member`) | Objets groupe descendants |
| Groupe d'administration de BornToShare (ex. `ADMIN-BORNTOSHARE`), s'il est rangé dans cette OU | **Refus** d'écrire `member` | Cet objet seulement |

Le refus explicite protège le groupe qui donne le rôle d'administrateur de BornToShare : sans lui, le compte de
provisioning pourrait faire de n'importe qui un administrateur de l'application. Le plus simple reste de ranger ce
groupe ailleurs que dans l'OU des groupes d'accès.

La lecture des groupes et des utilisateurs n'a pas à être déléguée : elle est accordée par défaut.

### Poser la délégation (PowerShell, module ActiveDirectory)

```powershell
$ou   = 'AD:OU=B2S Groups,OU=CORP,DC=corp,DC=local'
$sid  = New-Object Security.Principal.SecurityIdentifier (Get-ADUser svc-b2s-prov).SID
$grp  = [guid]'bf967a9c-0de6-11d0-a285-00aa003049e2'   # classe group
$mem  = [guid]'bf9679c0-0de6-11d0-a285-00aa003049e2'   # attribut member
$acl = Get-Acl $ou
$acl.AddAccessRule((New-Object DirectoryServices.ActiveDirectoryAccessRule($sid, 'CreateChild', 'Allow', $grp, 'None')))
$acl.AddAccessRule((New-Object DirectoryServices.ActiveDirectoryAccessRule($sid, 'WriteProperty', 'Allow', $mem, 'Descendents', $grp)))
Set-Acl -Path $ou -AclObject $acl

$admin = 'AD:CN=ADMIN-BORNTOSHARE,OU=B2S Groups,OU=CORP,DC=corp,DC=local'
$acl = Get-Acl $admin
$acl.AddAccessRule((New-Object DirectoryServices.ActiveDirectoryAccessRule($sid, 'WriteProperty', 'Deny', $mem, 'None')))
Set-Acl -Path $admin -AclObject $acl

Set-ADAccountControl -Identity svc-b2s-prov -AccountNotDelegated $true
```

Équivalent avec `dsacls` :

```bat
dsacls "OU=B2S Groups,OU=CORP,DC=corp,DC=local" /G "CORP\svc-b2s-prov:CC;group"
dsacls "OU=B2S Groups,OU=CORP,DC=corp,DC=local" /I:S /G "CORP\svc-b2s-prov:WP;member;group"
dsacls "CN=ADMIN-BORNTOSHARE,OU=B2S Groups,OU=CORP,DC=corp,DC=local" /D "CORP\svc-b2s-prov:WP;member"
```

Avant toute modification, sauvegarder les ACL : `(Get-Acl 'AD:<DN>').Sddl | Set-Content <fichier>.sddl` pour chaque
objet touché. On revient en arrière avec `Set-Acl` et l'objet relu depuis ce SDDL.

### Ce qu'il ne faut pas donner

| À éviter | Pourquoi |
|---|---|
| Contrôle total, ou « lire et écrire toutes les propriétés » sur les groupes | Le compte pourrait réécrire `sAMAccountName`, `adminCount`, `altSecurityIdentities`… (111 attributs au lieu d'un) |
| `DeleteChild` | BornToShare ne supprime pas de groupe ; une suppression ne se rattrape pas |
| Délégation sur une OU plus haute (`OU=CORP`, la racine du domaine) | Elle s'hérite sur tout : groupes de tier, comptes de service, serveurs. Un compte qui peut écrire `member` sur `T0-Comptes` devient administrateur du tier 0 |
| Délégation au compte du serveur de fichiers | Il n'écrit rien dans l'AD ; un compte de serveur avec des droits AD est un chemin d'élévation |

Les groupes d'accès créés ou adoptés doivent se trouver dans l'OU déléguée. Un groupe adopté ailleurs reste lisible,
mais BornToShare ne peut plus en changer les membres : le déplacer dans l'OU des groupes.

## L'OU des groupes, vérifiée avant chaque approbation

L'OU où un groupe sera créé vient de la zone (Zones › Provisionnement), sinon de l'annuaire. BornToShare vérifie
qu'elle est bien déléguée **avant** qu'un gardien approuve :

- le contrôle de santé (toutes les 5 minutes) lit, avec le compte `svc-b2s-prov`, l'attribut calculé
  `allowedChildClassesEffective` de chaque OU utilisée : l'AD y liste les classes que ce compte peut y créer. Le
  résultat apparaît dans Observabilité › Santé, une ligne « Group OU » par OU ;
- un refus de création récent (`AD_GROUP_CREATE_DENIED`) compte aussi ; l'information la plus récente l'emporte ;
- l'aperçu d'approbation affiche alors le blocage `GROUP_OU_NOT_DELEGATED`, et la route d'approbation le refuse
  (409) : on ne découvre plus le refus de l'AD après la décision du gardien.

## Le compte du serveur de fichiers

Il est **administrateur local** du serveur de fichiers, et rien de plus. C'est nécessaire pour :

| Usage | Protocole |
|---|---|
| Lire et poser les ACL NTFS, rompre ou rétablir l'héritage | SMB 445 (`smbcacls`) |
| Créer et supprimer dossiers et partages | SMB 445, RPC (`rpcclient`) |
| Mesurer les dossiers, scanner la sensibilité, module 5S | WinRM 5985, Kerberos uniquement (pas de NTLM, pas de délégation) |
| Lire et poser les quotas FSRM | WinRM 5985 ; FSRM exige un administrateur local |
| Lire les droits des fichiers sensibles | SMB 445 (`smbcacls`) |

WinRM en Kerberos demande le nom DNS du serveur (SPN `HTTP/<nom>`) : déclarer le serveur par son adresse IP reste
possible, BornToShare retrouve alors son nom dans le DNS du domaine.

Sans quotas FSRM ni création de partages, un compte non administrateur peut suffire : contrôle total NTFS sur les
dossiers partagés et sur les partages, membre de « Utilisateurs de gestion à distance » pour WinRM. Ce montage n'a
pas été validé sur le laboratoire.

## DFS

La lecture des espaces de noms passe par LDAP (`CN=Dfs-Configuration,CN=System`) et les référencements SMB :
aucun droit à ajouter. Créer ou supprimer des dossiers DFS depuis BornToShare demande une délégation de gestion de
l'espace de noms (console DFS › Déléguer les autorisations de gestion), à n'accorder que si cette fonction est utilisée.

## Vérifier

Les attributs calculés de l'AD donnent les droits **effectifs** d'un compte, en se connectant avec lui :

| Attribut, lu en se connectant avec le compte | Attendu pour `svc-b2s-prov` |
|---|---|
| `allowedChildClassesEffective` sur `OU=B2S Groups` | `group` |
| `allowedChildClassesEffective` sur `OU=CORP` et les autres OU | vide |
| `allowedAttributesEffective` sur un groupe de `OU=B2S Groups` | `member` seulement |
| `allowedAttributesEffective` sur `ADMIN-BORNTOSHARE` | vide |

Recette passée sur le laboratoire le 12 novembre 2026, avec les vrais comptes (14 contrôles, tous conformes) :

| Action | Attendu |
|---|---|
| `svc-b2s-prov` crée un groupe dans `OU=B2S Groups`, y ajoute puis retire un membre | autorisé |
| `svc-b2s-prov` change la description d'un groupe de l'application | refusé |
| `svc-b2s-prov` ajoute un membre à `ADMIN-BORNTOSHARE` ou à `T1-Comptes` | refusé |
| `svc-b2s-prov` crée un groupe dans `OU=CORP` | refusé |
| `svc-b2s-prov` supprime un groupe | refusé |
| `userfiler01` s'ajoute à `T0-Comptes`, crée un groupe, écrit sur un compte de service | refusé |
| `svc-b2s-sync` et `svc-b2s-auth` lisent les groupes et leurs membres | autorisé |
| Accès SMB et WinRM (Kerberos) du compte du serveur, marqué non délégable | autorisé |

## Messages liés aux droits

| Code | Cause | Correction |
|---|---|---|
| `GROUP_OU_NOT_DELEGATED` | L'OU de la zone n'est pas déléguée au compte de provisioning (vu avant l'approbation) | Déléguer l'OU comme ci-dessus, ou choisir l'OU des groupes dans la zone |
| `AD_GROUP_CREATE_DENIED` | L'AD a refusé la création du groupe | Délégation `CreateChild group` |
| `AD_MEMBER_WRITE_DENIED` | L'AD a refusé de changer les membres | Délégation `WriteProperty member` ; groupe hors de l'OU déléguée : le déplacer |
| `AD_TARGET_OU_NOT_FOUND` | L'OU n'existe pas | Créer l'OU ou corriger la zone |
| `SERVER_UNREACHABLE` | Le serveur ne répond plus (3 échecs de connexion de suite) | Voir [infrastructure.md](infrastructure.md#serveur-injoignable) |

## Référence : le laboratoire CORP.LOCAL

| Objet | État |
|---|---|
| `OU=B2S Groups,OU=CORP` | `svc-b2s-prov` : `CreateChild group` (cette OU) et `WriteProperty member` (groupes descendants) ; rien d'autre |
| `CN=ADMIN-BORNTOSHARE` | refus `WriteProperty member` pour `svc-b2s-prov` |
| `OU=CORP` | aucune entrée pour les comptes de BornToShare |
| `svc-b2s-sync`, `svc-b2s-auth`, `svc-b2s-prov`, `userfiler01` | non délégables, sans SPN |
| FILER01 | `userfiler01` administrateur local |
| Sauvegarde des ACL d'avant | `C:\B2S-ACL-Backup\20261112-161508` sur AD01 (SDDL par objet) |
