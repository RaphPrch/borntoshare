# Connexion avec Keycloak (SSO)

Administration › Settings › Infrastructure › **Keycloak**. Chaque serveur activé ajoute un bouton
« Se connecter avec votre organisation » sur la page de connexion. Protocole : OpenID Connect, code d'autorisation avec PKCE.

## Côté Keycloak

1. Dans le realm, créer un client **OpenID Connect** (par exemple `borntoshare`) :
   - « Client authentication » activé (client confidentiel), « Standard flow » activé ;
   - **Valid redirect URIs** : l'URI affichée dans le formulaire BornToShare, `https://<borntoshare>/sso/callback` ;
   - PKCE : méthode `S256` (Advanced › Proof Key for Code Exchange).
2. Copier le secret du client (onglet Credentials).
3. Créer les rôles du realm (ou des groupes) qui donnent l'accès, par exemple `b2s-admins`, et les attribuer.

## Côté BornToShare

| Champ | Exemple |
|---|---|
| URL du serveur | `https://sso.example.com` (sans `/realms/…`) |
| Realm | `example` |
| Client ID / secret | `borntoshare` / secret du client (chiffré en base) |
| Les rôles viennent de | rôles du realm (`realm_access.roles`), rôles du client, groupes (mapper « groups »), ou autre claim |
| Correspondances | `b2s-admins` → Administrateur de la plateforme |
| Quand rien ne correspond | refuser la connexion (recommandé), ou donner un rôle |
| Comptes de l'annuaire | même nom d'utilisateur qu'une identité AD importée : cette identité est utilisée, avec ses rôles BornToShare |

« Tester » vérifie la découverte OpenID du realm et le client (ID et secret), sans connecter personne.

## Accès à la connexion

1. Identité déjà créée par ce serveur : ses rôles suivent ceux du jeton à **chaque** connexion. Plus de rôle correspondant : connexion refusée.
2. Sinon, si « comptes de l'annuaire » est activé : identité AD importée de même nom d'utilisateur (ou e-mail).
3. Sinon : une identité est créée quand le jeton porte un rôle mis en correspondance (ou qu'un rôle par défaut est choisi).
4. Sinon : « Ce compte n'est pas autorisé dans BornToShare ».

Les identités créées par SSO se connectent uniquement par Keycloak, jamais par mot de passe. Les rôles donnés à la main
sur ces identités sont conservés ; seuls ceux venant du jeton sont recalculés.

## Sécurité

- `state` à usage unique (10 min), `nonce` et PKCE `S256` ; retour uniquement vers une page de BornToShare.
- Jetons reçus directement du point d'accès token de Keycloak, en TLS, avec authentification du client ; émetteur, audience,
  expiration et nonce de l'ID token vérifiés.
- Certificat du serveur Keycloak vérifié ; autorité privée : `capsule-runner/certs/oidc-ca.pem`, lue par auth-service.
- Avec plusieurs instances d'auth-service, `SESSION_STORE_BACKEND=redis` (les connexions en cours y sont gardées).

## Supervision et audit

Le health check contrôle la découverte OpenID de chaque serveur depuis un worker. Sont tracés : serveur ajouté, modifié, supprimé ;
connexions SSO réussies et refusées (motif) ; identité créée par SSO.
Supprimer un serveur désactive les identités qu'il a créées (historique conservé).

## Rôles depuis les groupes de l'Active Directory

Keycloak lit l'AD (fédération LDAP) et transforme l'appartenance à un groupe en rôle du realm, que BornToShare met en
correspondance avec ses propres rôles :

1. User Federation › LDAP : vendor « Active Directory », `ldaps://<dc>:636`, **lecture seule** (`READ_ONLY`), compte de
   liaison `svc-b2s-auth` (aucun droit ajouté dans l'AD, voir [droits-ad.md](droits-ad.md)), Users DN la racine du
   domaine, filtre `(&(objectCategory=person)(objectClass=user))`, nom d'utilisateur `sAMAccountName`, UUID `objectGUID`.
   L'autorité de l'AD doit être dans le truststore de Keycloak (`KC_TRUSTSTORE_PATHS`).
2. Mapper `group-ldap-mapper` : Groups DN `OU=B2S Groups,…`, filtre sur le seul groupe voulu (`(cn=<groupe>)`),
   `LOAD_GROUPS_BY_MEMBER_ATTRIBUTE`, lecture seule ; puis « Sync LDAP groups to Keycloak ».
3. Groupe synchronisé › Role mapping : rôle du realm `b2s-admins`.
4. Dans BornToShare : rôles depuis `realm_access.roles`, `b2s-admins` → Administrateur de la plateforme.

Ainsi, retirer quelqu'un du groupe AD lui retire l'accès à sa prochaine connexion (rôles recalculés à chaque fois).

## Laboratoire (hôte de build)

Recette du 2026-11-17 : Keycloak 26.3 en conteneur `lab-keycloak` (réseau `b2s-app`, HTTPS 8443, autorité de labo),
realm `corp`, client `borntoshare`, serveur « Keycloak CORP » dans BornToShare. « Tester » : découverte OK, client
reconnu ; « Se connecter avec CORP (Keycloak) » mène à la page de connexion du realm.

- auth-service tourne avec Python 3.13, qui vérifie les certificats en mode strict : l'autorité privée doit porter
  `basicConstraints=critical,CA:TRUE`, `keyUsage=keyCertSign`, et le certificat du serveur `subjectKeyIdentifier` /
  `authorityKeyIdentifier`. Sinon « Certificat du serveur Keycloak refusé » alors que `curl` l'accepte.
  Contrôle : `openssl verify -x509_strict -CAfile oidc-ca.pem tls.crt`.
- Le nom (ou l'IP) de l'URL du serveur doit figurer dans le SAN du certificat, et être joignable depuis auth-service
  comme depuis les navigateurs (même émetteur des deux côtés).
