# Auth-Service Modern v3.1 (Fix)

✅ Cette version corrige la v3 précédente qui était incomplète (il manquait `app/main.py` et les routes).
✅ Basée sur la v2, mais avec **Redis optionnel** et **flags de sécurité** pilotés par `.env`.

## Points clés
- Cookie session opaque `b2s_session`
- Providers: Keycloak primary → AD fallback → Local fallback → Dev optionnel
- Session store: `SESSION_STORE=inmemory|redis`
- Flags sécurité: `ENABLE_DEV_PROVIDER`, `ENABLE_CHANGE_PASSWORD`, `KEYCLOAK_VALIDATE_JWT`

## Démarrage
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Multi-provider (DEV / V1)

Ce service supporte **plusieurs méthodes d'authentification** en parallèle :

- `local` : comptes locaux (bootstrap / break-glass) via DAL
- `ad` : AD/LDAP **direct** (optionnel)
- `keycloak` : IdP OIDC (optionnel) — recommandé en production
- `dev` : provider de test (DEV uniquement)

### Sélection du provider
Le front/gateway peut sélectionner le provider via `provider` dans le body de login :

```json
{ "username": "alice", "password": "***", "provider": "ad" }
```

Si `provider` est absent, on utilise `DEFAULT_AUTH_PROVIDER` (par défaut `local`).

### Activer AD/LDAP (DEV)
Par défaut, AD est désactivé.

- `AD_ENABLED=true`
- `AD_URL=ldap://...` (ou **ldaps://...** en prod)
- `AD_BASE_DN=DC=...`
- soit `AD_USER_DN_TEMPLATE=CN={username},...`
- soit `AD_BIND_USER` + `AD_BIND_PASSWORD` pour search+bind

> En production, privilégier **OIDC via IdP** (Keycloak/AzureAD/ADFS) plutôt que d'exposer LDAP directement aux applications.
