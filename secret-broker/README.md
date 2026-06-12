# Secret Broker (Core V1)

Service interne chargé de la **résolution** et du **stockage persistant chiffré** des secrets.

## Périmètre V1
- Provider persistant officiel : `sm://` (filesystem chiffré)
- Provider optionnel dev : `env://` (désactivé par défaut)
- Aucune intégration `vault://`, `file://` ou provider non implémenté
- Requêtes internes uniquement (`X-Internal-Token`)

## Endpoints supportés
- `POST /resolve`
- `POST /secrets/store` (dev/ops uniquement, contrôlé par config)
- `POST /secrets/rotate` (dev/ops uniquement)
- `POST /secrets/revoke` (dev/ops uniquement)
- `GET /secrets/exists?ref=sm://...`

## Codes d'erreurs métiers

Le broker retourne une structure stable:

```json
{
  "error": {
    "code": "SECRET_NOT_FOUND",
    "message": "Secret not found",
    "ref": "sm://storage-endpoint/smb/192.168.100.40",
    "provider": "filesystem"
  }
}
```

Mapping HTTP :

- `400` → `SECRET_INVALID_REF`
- `404` → `SECRET_NOT_FOUND`
- `409` → `SECRET_DECRYPT_FAILED`
- `500` → `SECRET_PROVIDER_FAILURE` / `SECRET_PERSISTENCE_FAILURE`
- `403` → `SECRET_STORE_REJECTED`

## Persistance disque: permissions du bind-mount (important)

Le service tourne en utilisateur non-root (`UID 10004`).
Si le dossier hôte monté sur `/data/secrets` n'est pas inscriptible,
le service échoue explicitement (`SECRET_PERSISTENCE_FAILURE`) et ne démarre pas
en mode semi-fonctionnel.

Dans [`podman-compose.yml`](services/secret-broker/podman-compose.yml), le volume doit inclure:

```yaml
./secrets:/data/secrets:rw,Z,U
```

- `Z` : relabel SELinux
- `U` : remap ownership pour l'UID/GID du conteneur (rootless Podman)

## Variables d'environnement

- `INTERNAL_TOKEN` (obligatoire)
- `B2S_SECRET_ALLOWED_PREFIXES=sm://` (prod par défaut)
- `B2S_SECRET_ALLOW_ENV_PROVIDER=false` (mettre `true` uniquement en dev si `env://` est souhaité)
- `B2S_SECRET_PROVIDER=filesystem`
- `B2S_SECRETS_DIR=/data/secrets`
- `B2S_SECRET_MASTER_KEY` (**obligatoire**, stable entre redémarrages)
- `B2S_SECRET_ALLOW_WRITE=false` (à activer explicitement si nécessaire)
- `B2S_SECRET_WRITE_TOKEN=<token>` (recommandé dès que write est activé)

## Contrat inter-services

Les services appelants doivent utiliser le broker comme source de vérité des `sm://`:

- `frontend-service`, `auth-service`, `capsule-runner`, `governance-service` doivent appeler `POST /resolve` avec `X-Internal-Token`.
- Les refs recommandées sont de la forme :
  - `sm://storage-endpoint/smb/<endpoint-key>`
  - `sm://identity-source/ldap/<identity-key>`
  - `sm://capsule/<purpose>/<name>`

Le broker ne lit pas de secret métier depuis les compose des clients ; il ne reçoit que des références et des tokens de service.

Le broker fait des boot checks au démarrage:

1. clé maître chargée
2. dossier secrets existant/créable
3. dossier lisible/écrivable

En cas d’échec, le service crash explicitement.

Après modification :

```bash
podman compose -f podman-compose.yml up -d --build
```

Puis recréer les secrets DEV nécessaires (les secrets non persistés précédemment ne sont pas récupérables).

## Exemples
```bash
curl -s -X POST http://secret-broker:8010/resolve \
  -H 'X-Internal-Token: change-me' \
  -H 'Content-Type: application/json' \
  -d '{"ref":"sm://identity-source/ldap/main-bind"}'
```
