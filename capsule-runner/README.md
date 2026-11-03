# capsule-runner (worker)

Le seul conteneur qui agit sur l'Active Directory, les serveurs de fichiers et le DFS. Il lit les travaux
publiés par core-service dans Redis, résout le mot de passe nécessaire auprès de core-service, exécute l'action,
puis rend le résultat. Un agent HTTP(S) répond aux vérifications de santé de core-service.

| | |
|---|---|
| Image | `b2s-capsule-runner` (Python 3.14, Dramatiq ; `smbclient`, `rpcclient`, `smbcacls`, `krb5-user`), utilisateur 10003 |
| Processus | `start.sh` : l'agent (uvicorn) et le worker Dramatiq ; l'un qui s'arrête arrête le conteneur |
| Ports | Agent 8443 en HTTPS (avec `AGENT_TLS_CERT`/`AGENT_TLS_KEY`), sinon 8080 en HTTP (réseau interne uniquement) |
| Réseaux | `b2s-app` (vers core-service et l'extérieur), `b2s-jobs` (Redis) |
| Files | `capsule_identity` (annuaire), `capsule_probes` (tests, lectures), `capsule_acl` (groupes, ACL, dossiers, partages, DFS) |
| Sorties | LDAPS 636 / LDAP 389, Kerberos 88, DNS 53, SMB 445 (voir [docs/architecture.md](../docs/architecture.md#flux-à-ouvrir-vers-lextérieur)) |

## Actions

| Domaine | Actions |
|---|---|
| Annuaire | `test_ldap`, `test_ldaps`, `fetch_tls_certificate`, `discover_directory`, `collect_directory_snapshot`, `search_ldap(s)_principals`, `discover_group_users_recursive`, `test_kerberos` |
| Groupes AD | `ensure_ad_group`, `ensure_ad_group_member`, `remove_ad_group_member`, `grant_ad_access` |
| Serveurs de fichiers | `test_smb_ntlm`, `discover_smb_server`, `test_smb_root_access`, `acl_apply_via_group`, `folder_inheritance`, `folder_create`, `folder_delete`, `share_create`, `share_delete` |
| DFS | `read_dfs_namespaces`, `dfs_folder_create`, `dfs_folder_delete` |
| Réseau, santé | `resolve_name`, `infra_health_check` |

Chaque action est déclarée dans `app/core/action_registry.py` (schéma des paramètres), `app/core/scope_guard.py`
(droit minimal `read` ou `write`) et le contrat des travaux (`app/shared/b2s_job_contracts`, copie identique à
celle de core-service). Le test `test_action_wiring.py` vérifie que rien ne manque.

## Règles

- `RUNNER_MAX_SCOPE=read` refuse toute action de modification : c'est un worker de lecture seule.
- Un refus (droits, nom invalide, doublon) n'est pas relancé ; un délai dépassé l'est, sauf pour un test lancé
  depuis l'écran, qui échoue tout de suite.
- Un groupe supprimé hors BornToShare n'a plus de membres : la révocation aboutit.
- Supprimer un partage ne supprime jamais de fichiers ; le dossier part seulement s'il est vide et si on le demande.
- Les noms Windows (dossier, partage, dossier DFS) suivent `app/shared/windows_names.py`, identique à celui de core-service.

## Variables

`APP_ENV`, `INTERNAL_TOKEN`, `CAPSULE_BROKER_URL`, `RUNNER_MAX_SCOPE`, `AGENT_TLS_CERT`, `AGENT_TLS_KEY`,
`AGENT_PORT`. Certificats : [certs/README.md](certs/README.md).

## Tests

```bash
cd capsule-runner && python -m pytest -q
```
