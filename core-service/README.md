# core-service

Le cœur de BornToShare : données, règles de gouvernance, audit, coffre des secrets et planificateur. Il décide
et trace ; il ne parle jamais à l'AD ni aux serveurs : il publie des travaux que le worker exécute.

| | |
|---|---|
| Image | `b2s-core-service` (Python 3.14, FastAPI, SQLAlchemy, Dramatiq), utilisateur 10002 |
| Port | 8000, interne (réseaux `b2s-app`, `b2s-data`, `b2s-jobs`) ; API sous `/api` |
| Appelé par | frontend-service (routes métier), auth-service et capsule-runner (routes `/api/internal/*`) — toujours avec le jeton interne |
| Appelle | MariaDB (`borntoshare`, `borntoshare_logging`), Redis (base 2, publication), l'agent des workers |
| Montages | `capsule-runner/certs` (lecture seule) ; secrets podman `b2s_db_core`, `b2s_redis`, `b2s_master_key` (`/run/secrets`) |
| Santé | `GET /health` : 503 si la base ou Redis ne répond pas |

## Organisation du code

| Dossier | Contenu |
|---|---|
| `app/api/` | Routes : zones, annuaires, serveurs (`storage_endpoints`), dossiers (`storage_roots`), demandes, tags, infrastructure, réseau, observabilité ; `internal_*` pour les autres services |
| `app/api/governance/` | Orchestration des demandes (validation, révocation, expiration) ; n'accède jamais à la base directement |
| `app/services/` | Règles métier : `probe_service` (travaux), `secret_store` (coffre), `activity_bridge` (audit), `dfs_links`, `windows_names`, `infrastructure_service`, `sensitivity`, `scans` (mesures), `policies`, `notifications` et `mail_templates` (e-mails), `server_breaker` (serveur injoignable), `group_ou_check` (OU déléguée), `request_suggestions` |
| `app/jobs/` | Contrat des travaux, publication, planificateur (`infra_scheduler`), expiration des accès, chien de garde des travaux |
| `app/data/` | Modèles et dépôts (lecture par vues SQL) |

## Ce qu'il porte

- **Travaux** : chaque action sur l'AD ou un serveur devient une ligne `provisioning_jobs` puis un message
  Dramatiq. Le worker rend le résultat par `/api/internal/provisioning/jobs/*`.
- **Coffre** : `secret_items`, chiffré en AES-GCM par la clé `B2S_SECRET_MASTER_KEY` (secret podman `b2s_master_key`) ; `/api/internal/secrets/resolve`
  pour le worker.
- **Audit** : `borntoshare_logging.audit_event`, chaîné par hachage. Les refus sont tracés avec leur objet.
- **Planificateur** : `health_check`, `data_sync`, `access_expiry`, `dfs_read`, `policies` (voir [docs/architecture.md](../docs/architecture.md#planificateur)).
- **E-mails** : demandes, décisions, rappels, alertes, en HTML et en texte ([docs/notifications.md](../docs/notifications.md)).
- **Garde-fous des travaux** : un serveur injoignable n'est plus relancé en boucle (`server_breaker`) ; une approbation
  qui créerait un groupe dans une OU non déléguée est bloquée avant la décision (`group_ou_check`).
- **Module 5S** : routes internes pour le scanner (`internal_fives`), mesures gardées et rétablissables, alerte
  « dossier illisible » ([docs/module-5s.md](../docs/module-5s.md)).
- **Sans mode** : pas de documentation interactive de l'API, jamais de requête SQL dans les journaux.
- **Garde-fous** : un dossier ne se supprime pas tant qu'un accès court, un partage pas tant qu'un dossier géré
  est dedans, un hôte ne change pas sans déplacer les chemins, un espace de noms ne se déclare qu'une fois.

## Variables

Lues par pydantic-settings (`app/core/config.py`) : `INTERNAL_TOKEN`, `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (ou `DB_PASSWORD_FILE`, comme pour chaque mot de passe : lu par `app/secret_files.py`) et
`CAPSULE_BROKER_URL` sont obligatoires (le service refuse de démarrer sans eux) ; `DB_PORT`, `LOGGING_DB_NAME`
(la base d'audit reprend le serveur et le compte de `DB_*`), `B2S_SECRET_MASTER_KEY`, `B2S_RUNTIME_DIR` ; autorité privée des agents : `certs/agent-ca.pem`. Toute requête sauf `/health` exige le
jeton interne. Voir
[docs/installation.md](../docs/installation.md).

## Tests

Depuis la racine du dépôt (les tests de câblage lisent aussi le worker et le frontend) :

```bash
cd core-service && python -m pytest -q
```
