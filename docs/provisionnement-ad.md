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

### Compte de service

C'est le compte de la source d'identité AD liée à l'endpoint de stockage. Il ne doit pas être administrateur du domaine.
Sur l'OU de chaque zone, déléguer seulement :

```bat
dsacls "OU=B2S Groups,DC=corp,DC=example" /I:T /G "CORP\svc-borntoshare:CC;group"
dsacls "OU=B2S Groups,DC=corp,DC=example" /I:S /G "CORP\svc-borntoshare:WP;member;group"
```

- la 1ʳᵉ ligne autorise la création d'objets Groupe dans l'OU ;
- la 2ᵉ autorise l'écriture de l'attribut `member` des groupes de l'OU.

La lecture des utilisateurs, accordée par défaut aux utilisateurs authentifiés, suffit pour retrouver le demandeur.

Le compte de l'endpoint de stockage, qui applique l'ACL NTFS, doit pouvoir modifier les permissions des dossiers partagés.

### LDAPS vérifié

En production, capsule-runner vérifie le certificat des contrôleurs de domaine :

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
| `IDENTITY_SOURCE_INCOMPLETE` | hôte, compte, mot de passe ou DN de base manquant | compléter la source d'identité |
| `AD_BIND_FAILED` | le compte de service ne peut pas se connecter | vérifier compte et mot de passe |
| `AD_TLS_FAILED` | certificat du contrôleur refusé | vérifier `LDAP_CA_FILE` et le nom d'hôte |
| `AD_GROUP_CREATE_DENIED` | pas le droit de créer des groupes dans l'OU | délégation « CC;group » ci-dessus |
| `AD_MEMBER_WRITE_DENIED` | pas le droit de modifier les membres du groupe | délégation « WP;member » ci-dessus |
| `AD_GROUP_NAME_CONFLICT` | même nom hors de l'OU de la zone | adopter le groupe ou le renommer dans l'AD |
| `AD_PRINCIPAL_NOT_FOUND` | demandeur introuvable dans l'AD | vérifier le compte du demandeur |
| `AD_UNREACHABLE` | contrôleur de domaine injoignable | réseau ou DNS ; la tâche est relancée automatiquement |
| `AD_JOB_STILL_RUNNING` | l'AD n'a pas répondu dans le délai (90 s) | approuver à nouveau dans quelques minutes |
| `ACL_APPLY_FAILED` | le demandeur est dans le groupe, mais l'ACL n'a pas pu être posée | approuver à nouveau pour réappliquer |
