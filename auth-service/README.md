# auth-service

Connexion des utilisateurs et sessions. Il n'a pas de base de données propre : il lit les annuaires, les comptes
locaux et les rôles auprès de core-service (routes `/api/internal/*`, jeton interne) et range les sessions dans Redis.

| | |
|---|---|
| Image | `b2s-auth-service` (Python 3.14, FastAPI, uvicorn), utilisateur 10001 |
| Port | 8000, interne (réseaux `b2s-app`, `b2s-jobs`) |
| Appelé par | frontend-service (BFF) |
| Appelle | core-service, Redis (base 1), les contrôleurs de domaine (LDAPS), Keycloak (OIDC) |
| Santé | `GET /health` : 503 si Redis (sessions) ne répond pas |

## Fournisseurs de connexion

| Fournisseur | Fichier | Fonctionnement |
|---|---|---|
| Local | `services/providers/local_core.py` | Comptes créés dans BornToShare, mot de passe vérifié par core-service |
| AD / LDAP | `services/providers/ad_ldap.py` | Retrouve l'utilisateur avec le compte de la source, puis vérifie son mot de passe par un bind LDAPS ; rôles déduits de ses groupes |
| SSO Keycloak | `services/oidc.py`, `api/sso.py` | OIDC, code d'autorisation ; voir [docs/keycloak.md](../docs/keycloak.md) |

## Sessions

- Cookie `b2s_session` (HttpOnly) → session dans Redis (`bts:auth:*`, base 1), qui survit aux redémarrages.
- Cookie `b2s_principal` signé par `PRINCIPAL_SIGNING_KEY` (60 s), relu par le frontend à chaque requête.
- Limite de connexion : 5 échecs par compte, 50 par adresse, sur 15 minutes.
- Durées et sessions ouvertes : Réglages avancés › Sessions utilisateur (révocation possible).

## Variables

`INTERNAL_TOKEN`, `PRINCIPAL_SIGNING_KEY` (obligatoire : refus au démarrage de la clé par défaut), `REDIS_PASSWORD` (ou `REDIS_PASSWORD_FILE`, le secret podman `b2s_redis`) (et `SESSION_STORE_BACKEND=redis`,
`REDIS_DB=1` fixés par la composition) ; autorité privée de Keycloak : `certs/oidc-ca.pem`. Voir
[docs/installation.md](../docs/installation.md).

Comptes de l'annuaire et droits nécessaires : [docs/droits-ad.md](../docs/droits-ad.md) ; rôles donnés par les groupes AD :
[docs/provisionnement-ad.md](../docs/provisionnement-ad.md#connexion-des-utilisateurs-ad-et-rôles-par-groupe).
