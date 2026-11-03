# core-service

Le cœur de BornToShare : données, règles de gouvernance, audit, coffre des secrets et planificateur. Il décide
et trace ; il ne parle jamais à l'AD ni aux serveurs : il publie des travaux que le worker exécute.

| | |
|---|---|
| Image | `b2s-core-service` (Python 3.14, FastAPI, SQLAlchemy, Dramatiq), utilisateur 10002 |
| Port | 8000, interne (réseaux `b2s-app`, `b2s-data`, `b2s-jobs`) ; API sous `/api` |
| Appelé par | frontend-service (routes métier), auth-service et capsule-runner (routes `/api/internal/*`) |
| Appelle | MariaDB (`borntoshare`, `borntoshare_logging`), Redis (base 2, publication), l'agent des workers |
| Montages | `config/runtime` (connexion à la base choisie dans l'application), `capsule-runner/certs` (lecture seule) |
| Santé | `GET /health` |

## Organisation du code

| Dossier | Contenu |
|---|---|
| `app/api/` | Routes : zones, annuaires, serveurs (`storage_endpoints`), dossiers (`storage_roots`), demandes, tags, infrastructure, réseau, observabilité ; `internal_*` pour les autres services |
| `app/api/governance/` | Orchestration des demandes (validation, révocation, expiration) ; n'accède jamais à la base directement |
| `app/services/` | Règles métier : `probe_service` (travaux), `secret_store` (coffre), `activity_bridge` (audit), `dfs_links`, `windows_names`, `infrastructure_service` |
| `app/jobs/` | Contrat des travaux, publication, planificateur (`infra_scheduler`), expiration des accès, chien de garde des travaux |
| `app/data/` | Modèles et dépôts (lecture par vues SQL) |

## Ce qu'il porte

- **Travaux** : chaque action sur l'AD ou un serveur devient une ligne `provisioning_jobs` puis un message
  Dramatiq. Le worker rend le résultat par `/api/internal/provisioning/jobs/*`.
- **Coffre** : `secret_items`, chiffré en AES-GCM par `B2S_SECRET_MASTER_KEY` ; `/api/internal/secrets/resolve`
  pour le worker.
- **Audit** : `borntoshare_logging.audit_event`, chaîné par hachage. Les refus sont tracés avec leur objet.
- **Planificateur** : `health_check`, `data_sync`, `access_expiry`, `dfs_read` (voir [docs/architecture.md](../docs/architecture.md#planificateur)).
- **Garde-fous** : un dossier ne se supprime pas tant qu'un accès court, un partage pas tant qu'un dossier géré
  est dedans, un hôte ne change pas sans déplacer les chemins, un espace de noms ne se déclare qu'une fois.

## Variables

`APP_ENV`, `INTERNAL_TOKEN`, `B2S_SECRET_MASTER_KEY`, `DB_*`, `LOGGING_DB_*`, `CAPSULE_BROKER_URL`,
`B2S_RUNTIME_DIR`, `B2S_AGENT_CA_FILE`, `B2S_ALLOW_PUBLIC_API` (le BFF appelle les routes métier). Voir
[docs/installation.md](../docs/installation.md).

## Tests

Depuis la racine du dépôt (les tests de câblage lisent aussi le worker et le frontend) :

```bash
cd core-service && python -m pytest -q
```
