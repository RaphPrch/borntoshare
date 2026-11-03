# Sécurité

## Principes

- **Une seule entrée publique** : frontend-service (3000, derrière un proxy HTTPS). auth-service, core-service,
  le worker et Redis ne sont joignables que sur les réseaux Podman ; Redis est sur un réseau interne sans sortie.
- **Le worker est le seul à agir** sur l'AD et les serveurs de fichiers. core-service décide, trace et publie
  un travail ; il ne détient jamais de session LDAP ou SMB.
- **Moindre privilège** : chaque capacité a son compte (lecture de l'annuaire, connexion des utilisateurs,
  gestion des groupes, chaque serveur de fichiers, chaque espace de noms DFS).
- **Tout est tracé** : chaque décision, chaque changement et chaque refus est écrit dans `borntoshare_logging.audit_event`,
  chaîné par hachage SHA-256.

## Jetons, cookies et en-têtes

| Élément | Où | Rôle | Protection |
|---|---|---|---|
| `INTERNAL_TOKEN` | Tous les services | En-tête `X-Internal-Token` sur chaque appel entre services | Comparaison à temps constant ; refusé si absent ; jamais exposé au navigateur |
| Cookie `b2s_session` | Navigateur ↔ frontend | Session de l'utilisateur, stockée dans Redis (base 1) | `HttpOnly`, `Secure` en HTTPS, `SameSite=Lax` ; durées réglables (Réglages avancés › Sessions utilisateur) ; révocable |
| Cookie `b2s_principal` | Navigateur ↔ frontend | Identité et rôles de l'utilisateur, signés par `PRINCIPAL_SIGNING_KEY` | Signature vérifiée à chaque requête ; durée de 60 s : un changement de droits ou une révocation s'applique en une minute |
| Identité de l'utilisateur | frontend → core | En-têtes `X-Identity-Id`, `X-Roles`, posés par le BFF | core-service exige le jeton interne sur **toutes** ses requêtes (sauf `/health`) : sans lui, ces en-têtes ne sont pas lus (401). Le navigateur ne peut pas les forger |
| `B2S_SECRET_MASTER_KEY` | core-service | Chiffre les mots de passe stockés (AES-256-GCM, la référence du secret comme donnée associée) | Jamais en base ; à sauvegarder à part |
| Identifiants d'agent | core → worker | Vérification de la santé du worker | HTTPS avec `certs/agent.crt` et `agent.key` ; autorité privée `certs/agent-ca.pem` |
| Mot de passe Redis | auth, core, worker | Accès à la file et aux sessions | Réseau `b2s-jobs` interne |

Le BFF vérifie l'origine des requêtes qui modifient des données (contrôle CSRF de SvelteKit contre
`FRONTEND_PUBLIC_ORIGIN`). La connexion est limitée à 5 échecs par compte et 50 par adresse en 15 minutes.

## Coffre des secrets

Les mots de passe des comptes de service (annuaires, serveurs de fichiers, espaces DFS, SSO) ne sont jamais
stockés en clair :

1. le formulaire envoie le mot de passe une seule fois ;
2. core-service le chiffre avec la clé maîtresse et le range dans `secret_items` sous une référence `sm://…` ;
3. l'objet (serveur, annuaire…) ne garde que cette référence ;
4. au moment de s'en servir, le worker (ou auth-service, pour la connexion AD) demande à core-service
   (`/api/internal/secrets/resolve`, jeton interne) le mot de passe d'une référence, s'en sert, puis l'oublie ;
5. un secret qui n'est plus utilisé par aucun objet est supprimé.

Le test de santé planifié vérifie que chaque référence mène bien à un secret. Si ce n'est pas le cas (base
restaurée sans sa clé, coffre réinitialisé…), le tableau de bord des administrateurs nomme les objets à
ressaisir, et la fiche de chaque serveur propose « Ressaisir le mot de passe ».

## Comptes de service et droits à déléguer

| Compte | Utilisé pour | Droits minimaux |
|---|---|---|
| Lecture de l'annuaire (source AD) | Instantanés, recherche de personnes et de groupes | Utilisateur du domaine ; bind LDAPS |
| Connexion des utilisateurs (facultatif, dédié) | Retrouver l'utilisateur avant de vérifier son mot de passe | Utilisateur du domaine |
| Gestion des groupes AD (« Gérer les groupes AD ») | Créer les groupes d'accès, ajouter et retirer les membres | Sur l'OU des groupes de la zone : créer et supprimer des objets groupe, lire et écrire les propriétés des groupes (dont `member`) |
| Serveur de fichiers (un par serveur) | Lire les ACL, poser les ACE des groupes, créer et supprimer dossiers et partages | Administrateur local du serveur (accès à `C$`/`ADMIN$` et à l'API de partage) |
| Espace de noms DFS (un par espace) | Lire l'espace de noms ; créer ou supprimer des dossiers DFS | Lecture : utilisateur du domaine ; modification : gestion déléguée de l'espace de noms (console DFS › Déléguer les autorisations de gestion) |

Délégation sur l'OU des groupes, par exemple :

```powershell
dsacls "OU=B2S Groups,OU=CORP,DC=CORP,DC=LOCAL" /G "CORP\b2s:CCDC;group"
dsacls "OU=B2S Groups,OU=CORP,DC=CORP,DC=LOCAL" /I:S /G "CORP\b2s:RPWP;;group"
```

Un refus de l'AD ou du serveur est rendu tel quel, avec ce qu'il faut corriger. Par exemple : « le compte n'est
pas autorisé à créer des groupes dans cette OU », « doit être administrateur local du serveur », ou « déléguez-lui
la gestion de l'espace de noms ». BornToShare ne contourne jamais un refus.

## Protocoles vers l'AD et les serveurs

- **LDAPS (636)** : le chemin retenu partout. Le certificat du serveur est vérifié (autorité collée dans la
  fiche de l'annuaire, nom attendu si l'hôte est une adresse IP). Un AD durci (CIS L1) refuse le bind simple
  en clair sur 389.
- **SMB 3 (445)** : authentification NTLM avec le compte du serveur ; déclarer le serveur par son adresse IP
  si son nom n'a pas de SPN Kerberos.
- **DFS** : référencements SMB pour lire, RPC netdfs pour modifier, sur le serveur racine de l'espace.
- **Kerberos (88)** : test de connexion ; le worker ne fait jamais de délégation Kerberos.

## Conteneurs

Chaque service tourne :
- avec un utilisateur dédié non-root (UID 10001 à 10006, redis 999) ;
- avec un système de fichiers en lecture seule, et `/tmp` en tmpfs `noexec` ;
- sans aucune capacité Linux (`cap_drop: ALL`) et avec `no-new-privileges`.

Les seuls montages sont `capsule-runner/certs` (lecture seule) et `config/runtime` (core-service).
Les images partent d'une base fixée (`python:3.14-slim-trixie`, `node:26-alpine`).

## Rôles dans l'application

| Rôle | Peut |
|---|---|
| Administrateur de la plateforme | Tout : infrastructure, annuaires, serveurs, zones, dossiers, politiques, journaux |
| Gardien d'un dossier | Valider, refuser, prolonger et révoquer les accès à ses dossiers |
| Utilisateur | Demander un accès, suivre et annuler ses demandes, voir ses accès |

Un gardien ne valide pas sa propre demande : un autre gardien ou un administrateur le fait.

## Audit

- Chaque événement porte son auteur, son objet (dossier, serveur, zone, demande), son résultat et son contexte.
- Les refus sont tracés une seule fois, rattachés à l'objet visé.
- Les lignes sont chaînées (`hash_prev` → `hash_current`) : une ligne modifiée ou supprimée casse la chaîne.
  On ne réécrit jamais l'historique ; une correction est un nouvel événement.
- La rétention se règle dans Réglages avancés › Journalisation (purge quotidienne tracée).

## À faire en production

- Secrets générés aléatoirement (`PRINCIPAL_SIGNING_KEY` est refusée si c'est la clé par défaut), `.env` en `chmod 600`.
- HTTPS devant le port 3000, et `FRONTEND_PUBLIC_ORIGIN` en `https://`.
- Agent du worker en HTTPS (`capsule-runner/certs/agent.crt` et `agent.key`).
- `make wizard-down` dès la fin de l'installation.
- Sauvegarde des bases (`make backup`) **et**, à part, de `B2S_SECRET_MASTER_KEY`.
- Comptes de service dédiés, mots de passe longs, droits limités à ce tableau.
