# Connexion avec Keycloak (SSO)

Administration › Paramètres avancés › Infrastructure › **Keycloak**. Chaque serveur activé ajoute un bouton
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
- Certificat du serveur Keycloak vérifié ; autorité privée : `B2S_OIDC_CA_FILE` sur auth-service.
- Avec plusieurs instances d'auth-service, `SESSION_STORE_BACKEND=redis` (les connexions en cours y sont gardées).

## Supervision et audit

Le health check contrôle la découverte OpenID de chaque serveur depuis un worker. Sont tracés : serveur ajouté, modifié, supprimé ;
connexions SSO réussies et refusées (motif) ; identité créée par SSO.
Supprimer un serveur désactive les identités qu'il a créées (historique conservé).
