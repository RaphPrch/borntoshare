# AD de test (tests de bout en bout)

`testing/ad-lab` fournit un contrôleur de domaine **Samba 4 AD** prêt à l'emploi, `adlab.example.test`,
pour tester BornToShare de bout en bout sans Active Directory Windows. **Jamais en production.**

Samba AD parle les mêmes protocoles qu'un AD Windows, ceux qu'utilise le worker : LDAP et LDAPS, Kerberos, NTLM,
schéma AD (`sAMAccountName`, `objectGUID`, `groupType`, `member`), partages SMB avec ACL NTFS. Un vrai Windows
Server ne tourne pas en conteneur sur un hôte Linux. Différences connues : pas de GPO appliquées, ACL NTFS
stockées en attributs étendus (`acl_xattr`) ; sans effet sur BornToShare.

## Démarrer

```
make up            # la stack BornToShare (le labo rejoint son réseau b2s-app)
make ad-lab-up     # construit et démarre le DC ; environ une minute au premier démarrage
make ad-lab-logs   # « ad-lab: share permissions set » = prêt
```

Puis déclarer le labo dans BornToShare (idempotent, peut être relancé) :

```
B2S_URL=https://<borntoshare> B2S_USER=<admin local> B2S_PASSWORD_FILE=<fichier du mot de passe> \
  python3 testing/ad-lab/register.py
```

Il crée la zone « AD lab » (groupes dans `OU=B2S Groups`), la source d'identité « AD lab » (LDAPS), le serveur de
fichiers « AD lab file server » et quatre storage roots (`corp\finance`, `corp\hr`, `corp\legal`, `projects`).
Les mots de passe vont dans le secret broker. Si une autre source authentifie déjà `example.test`, la source du
labo est créée sans la connexion des utilisateurs (garde-fou « un domaine, une source de connexion »).

`make ad-lab-down` arrête le DC (données gardées) ; `make ad-lab-reset` supprime aussi le domaine.

## Contenu

| | |
|---|---|
| Domaine | `EXAMPLE.TEST` (NetBIOS `EXAMPLE`), DC `adlab.example.test`, base `DC=example,DC=test` |
| `OU=Staff` | paul.martin (Projects), jane.doe et alice.finance (Finance), lucie.user (HR), claire.auditor (Audit), marc.admin (IT) |
| Groupes | GG_Finance, GG_HR, GG_Projects, GG_B2S_Admins (marc.admin) |
| `OU=Service Accounts` | `svc-b2s-read` (snapshot et connexion, lecture seule), `svc-b2s-prov` (groupes d'accès), `svc-b2s-files` (ACL des partages) |
| `OU=B2S Groups` | vide au départ : BornToShare y crée les groupes d'accès ; seul `svc-b2s-prov` y a les droits (délégation) |
| Partages | `\\adlab.example.test\corp` (finance, hr, legal) et `\\adlab.example.test\projects` (alpha, beta) |

Les ACL NTFS de départ ne donnent l'accès qu'aux administrateurs et à `svc-b2s-files` : sans groupe BornToShare,
personne n'entre. Un test peut donc vérifier l'accès réel, par exemple :

```
smbclient //adlab.example.test/corp -U 'EXAMPLE\paul.martin' -c 'cd finance; ls'
```

Mots de passe par défaut (labo uniquement), modifiables avant le premier démarrage :
`AD_LAB_ADMIN_PASSWORD` (Administrator), `AD_LAB_USER_PASSWORD` (utilisateurs), `AD_LAB_SERVICE_PASSWORD`
(comptes de service), dans l'environnement de `make ad-lab-up` ; voir `testing/ad-lab/compose.yml`.

## LDAPS vérifié

Le DC a sa propre autorité de certification, publiée dans `testing/ad-lab/out/ad-ca.pem`. Avec
`LDAP_TLS_VERIFY=true`, ajouter ce certificat au fichier `LDAP_CA_FILE` de capsule-runner et d'auth-service
(un fichier peut contenir plusieurs autorités). Les certificats respectent la vérification stricte de Python 3.13+.

## Scénario de bout en bout vérifié

Demande de lecture de paul.martin sur « Lab Finance » → aperçu (groupe `B2S_CORP_FINANCE_RX` à créer dans
`OU=B2S Groups`) → validation (groupe créé, membre ajouté, ACL posée, 3 s) → Paul lit `corp\finance`, ne peut pas
y écrire et n'accède pas à `corp\hr` → à l'échéance, la tâche d'expiration le retire du groupe et l'accès disparaît.
