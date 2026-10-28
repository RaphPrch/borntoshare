# Provisionnement Active Directory

À l'approbation d'une demande d'accès, BornToShare donne l'accès par un groupe AD :
un groupe global de sécurité par racine de stockage et par niveau (Lecture, Écriture).

## Ce qui se passe à l'approbation

Les étapes s'enchaînent dans l'ordre. Chacune attend la précédente et écrit une entrée
dans le journal de la demande (Demandes d'accès › tiroir de la demande › Journal de provisionnement).

1. **Groupe AD** (tâche `AD_ACCESS_GRANT` de capsule-runner, une seule connexion LDAP, donc un seul contrôleur de domaine) :
   - groupe déjà connu de BornToShare (GUID) : il est réutilisé ;
   - sinon, groupe du même nom dans l'OU de la zone : il est réutilisé ;
   - sinon, groupe du même nom **ailleurs** dans le domaine : conflit, rien n'est créé (voir Adoption) ;
   - sinon : création dans l'OU de la zone. C'est la 1ʳᵉ permission de ce niveau sur cette racine.
2. **Membre** : le demandeur est ajouté au groupe. S'il est déjà membre, ce n'est pas une erreur.
3. **ACL NTFS** : le groupe reçoit ses droits sur le partage (Lecture = lecture et exécution, Écriture = modification),
   hérités par les sous-dossiers et fichiers. Les droits sont réappliqués à chaque approbation, ce qui répare une ACL modifiée à la main.
4. La demande passe à « Appliquée » **seulement si toutes les étapes ont réussi**. Sinon elle reste en attente,
   avec le message d'erreur et l'action à mener dans le tiroir.

Une nouvelle approbation peut être lancée sans risque : rien n'est fait deux fois.

**Nom du groupe.** Il vient du modèle de nommage de la zone (Zones › Provisionnement), par exemple `{PREFIX}_{ROOTCODE}_{PERM}`
qui donne `B2S_CORP_FINANCE_RW`. Le nom est fixé à la 1ʳᵉ approbation, puis gardé : modifier le modèle ensuite ne renomme pas les groupes existants.
Il fait 64 caractères au plus, sans `" / \ [ ] : ; | = , + * ? < > @`.

**OU de création**, par ordre de priorité :
1. l'OU propre à l'endpoint de stockage, si elle est définie ;
2. l'OU de la zone (Zones › Provisionnement › Unité d'organisation) ;
3. l'OU par défaut de la source d'identité.

**Révocation et expiration.** L'utilisateur est retiré du groupe. Le groupe est conservé, même vide,
avec son ACL : il resservira à la prochaine demande.

## Adoption d'un groupe existant

Si un groupe porte déjà le nom attendu hors de l'OU de la zone (par exemple un groupe créé à la main avant BornToShare),
l'approbation s'arrête sur « Un groupe portant ce nom existe déjà ailleurs dans Active Directory » et affiche son DN.
Un administrateur de la plateforme peut cliquer sur **Adopter ce groupe et approuver** : BornToShare utilise alors ce groupe
pour ce niveau de cette racine, au lieu d'en créer un.

Le compte de service doit pouvoir modifier les membres du groupe adopté. Ce groupe étant hors de l'OU déléguée, il faut,
au choix, déléguer « Écrire l'attribut member » sur ce groupe, ou déplacer le groupe dans l'OU de la zone.

## Prérequis Active Directory

### Capacités et comptes de service

Chaque source d'identité AD active seulement les capacités dont elle a besoin
(Administration › Sources d'identité › Modifier, ou l'assistant de création) :

| Capacité | Rôle | Compte utilisé | Droits AD nécessaires |
|---|---|---|---|
| Inventaire par snapshot | collecte utilisateurs, groupes et appartenances | compte « snapshot » | lecture (par défaut pour un utilisateur authentifié) |
| Authentifier les utilisateurs | connexion à BornToShare avec le compte AD | compte « auth » | lecture |
| Importer les groupes | ajout de groupes AD et attribution de rôles | — | — |
| Gérer les groupes AD | création des groupes et des membres à l'approbation | compte « provisioning » | délégation ci-dessous |

Chaque capacité peut avoir son **compte dédié** (DN de liaison et mot de passe). Sans compte dédié, elle utilise le
compte principal de la source. On peut ainsi donner un compte en lecture seule à l'inventaire et à la connexion,
et réserver le compte délégué à la gestion des groupes.
Les mots de passe sont rangés dans le secret broker, un secret par compte. L'interface ne les relit jamais.

Si « Gérer les groupes AD » est désactivée, l'approbation s'arrête sur `AD_PROVISIONING_DISABLED`.

Le compte « provisioning » ne doit pas être administrateur du domaine. Sur l'OU de chaque zone, déléguer seulement :

```bat
dsacls "OU=B2S Groups,DC=corp,DC=example" /I:T /G "CORP\svc-b2s-prov:CC;group"
dsacls "OU=B2S Groups,DC=corp,DC=example" /I:S /G "CORP\svc-b2s-prov:WP;member;group"
```

- la 1ʳᵉ ligne autorise la création d'objets Groupe dans l'OU ;
- la 2ᵉ autorise l'écriture de l'attribut `member` des groupes de l'OU.

La lecture des utilisateurs, accordée par défaut aux utilisateurs authentifiés, suffit pour retrouver le demandeur.

Le compte de l'endpoint de stockage, qui applique l'ACL NTFS, doit pouvoir modifier les permissions des dossiers partagés.

## Connexion des utilisateurs AD et rôles par groupe

La capacité « Authentifier les utilisateurs » doit être active. L'utilisateur se connecte avec `utilisateur`,
`utilisateur@domaine` ou `DOMAINE\utilisateur`. Le nom de domaine de la source (déduit du DN de base s'il est vide)
sert à choisir la bonne source quand il y en a plusieurs.

L'AD vérifie le mot de passe. BornToShare donne ensuite l'accès :

- **utilisateur importé** (Identités › Créer › Utilisateur de l'annuaire) : accès avec son rôle ;
- **membre d'un groupe AD qui a un rôle** (Identités › Créer › Groupe de l'annuaire, puis choisir le rôle,
  par exemple Administrateur de la plateforme) : l'identité est créée à la 1ʳᵉ connexion. Les groupes imbriqués comptent ;
- sinon : refus « Ce compte n'est pas autorisé dans BornToShare ».

Les appartenances viennent du **dernier snapshot** de la source : après un ajout ou un retrait dans l'AD,
lancer une synchronisation (ou attendre la suivante). Un utilisateur entré par un groupe perd l'accès dès qu'un snapshot
montre qu'il n'est plus dans aucun groupe qui a un rôle. Un utilisateur importé explicitement garde son accès.

Si « Importer les groupes » est désactivée, les rôles donnés par les groupes ne s'appliquent plus.

### Test de connexion

« Tester la connexion » (et « Tester ce compte » pour un compte dédié) passe par capsule-runner :
le worker ouvre une connexion LDAP (389) ou LDAPS (636) vers le contrôleur de domaine, sans WinRM ni PowerShell.
Il vérifie dans l'ordre : la résolution DNS, la connexion (et le certificat en LDAPS), le bind du compte, la lecture du DN de base.
Le tiroir affiche le résultat de chaque étape et l'action à mener :

| Code | Cause |
|---|---|
| `LDAP_DNS_FAILED` | le nom du contrôleur ne se résout pas |
| `LDAP_UNREACHABLE` | port fermé ou contrôleur injoignable |
| `LDAP_TLS_FAILED` | certificat refusé (voir LDAPS vérifié) |
| `LDAP_SIGNING_REQUIRED` | le contrôleur exige un LDAP signé : passer en LDAPS |
| `LDAP_BIND_FAILED`, `LDAP_ACCOUNT_LOCKED`, `LDAP_ACCOUNT_DISABLED`, `LDAP_PASSWORD_EXPIRED`… | compte de service refusé, avec la raison donnée par l'AD |
| `LDAP_BASE_DN_NOT_FOUND` | DN de base inexistant ou illisible pour ce compte |

La vérification du certificat suit `LDAP_TLS_VERIFY`, comme le snapshot et la gestion des groupes. Si elle est désactivée,
le tiroir affiche « Connexion chiffrée » au lieu de « Certificat valide ».

auth-service se connecte directement au contrôleur pour authentifier les utilisateurs (sans passer par le worker, pour la latence de connexion).

### Journal d'audit

Sont tracés (Observabilité › Journal) : création, modification et suppression d'une source ; demande de snapshot (avec son auteur),
fin du snapshot (volumes) ou échec (raison) ; connexions réussies et refusées (motif : mot de passe, compte non autorisé…, jamais le mot de passe) ;
identité créée à la 1ʳᵉ connexion par un groupe qui a un rôle.

### LDAPS vérifié

En production, capsule-runner (gestion des groupes) et auth-service (connexion des utilisateurs) vérifient le certificat
des contrôleurs de domaine. Les deux lisent le même fichier :

1. déposer le certificat de l'autorité de certification AD (format PEM) dans `capsule-runner/certs/ad-ca.pem` ;
2. dans `.env` :

   ```
   LDAP_TLS_VERIFY=true
   LDAP_CA_FILE=/etc/b2s/certs/ad-ca.pem
   ```

3. renseigner, dans la source d'identité, le nom d'hôte présent dans le certificat du contrôleur de domaine (pas son adresse IP).

Le certificat doit contenir l'extension « Authority Key Identifier ». Les certificats émis par une autorité AD CS l'ont ;
certains certificats autogénérés ne l'ont pas et sont refusés (`AD_TLS_FAILED`).

## Messages d'erreur

| Code | Cause | Action |
|---|---|---|
| `ZONE_GROUP_OU_MISSING` | aucune OU pour les groupes de la zone | la définir dans Zones › Provisionnement |
| `AD_TARGET_OU_NOT_FOUND` | l'OU de la zone n'existe pas dans l'AD | corriger l'OU ou la créer |
| `IDENTITY_SOURCE_REQUIRED` | l'endpoint n'a pas de source d'identité AD | lier une source d'identité AD à l'endpoint |
| `AD_PROVISIONING_DISABLED` | « Gérer les groupes AD » est désactivée sur la source | l'activer sur la source d'identité |
| `IDENTITY_SOURCE_INCOMPLETE` | hôte, compte, mot de passe ou DN de base manquant | compléter la source d'identité |
| `AD_BIND_FAILED` | le compte de service ne peut pas se connecter | vérifier le compte « provisioning » (ou le compte principal) et son mot de passe |
| `AD_TLS_FAILED` | certificat du contrôleur refusé | vérifier `LDAP_CA_FILE` et le nom d'hôte |
| `AD_GROUP_CREATE_DENIED` | pas le droit de créer des groupes dans l'OU | délégation « CC;group » ci-dessus |
| `AD_MEMBER_WRITE_DENIED` | pas le droit de modifier les membres du groupe | délégation « WP;member » ci-dessus |
| `AD_GROUP_NAME_CONFLICT` | même nom hors de l'OU de la zone | adopter le groupe ou le renommer dans l'AD |
| `AD_PRINCIPAL_NOT_FOUND` | demandeur introuvable dans l'AD | vérifier le compte du demandeur |
| `AD_UNREACHABLE` | contrôleur de domaine injoignable | réseau ou DNS ; la tâche est relancée automatiquement |
| `AD_JOB_STILL_RUNNING` | l'AD n'a pas répondu dans le délai (90 s) | approuver à nouveau dans quelques minutes |
| `ACL_APPLY_FAILED` | le demandeur est dans le groupe, mais l'ACL n'a pas pu être posée | approuver à nouveau pour réappliquer |
