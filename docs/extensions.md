# Extensions (Réglages avancés › Extensions)

Les extensions relient BornToShare aux outils de l'infrastructure. Chacune se règle dans un panneau latéral avec
« Tester », puis s'active. Les événements envoyés (journal d'audit, nouvelles alertes de gouvernance) partent de
core-service en arrière-plan : 3 essais, journal des envois gardé 7 jours, visible dans le panneau.

| Catégorie | Extension | Ce qu'elle fait | Événements |
|---|---|---|---|
| Journalisation | Syslog, Splunk | journal d'audit et alertes vers le SIEM | audit, alertes |
| Supervision | Centreon | `GET /monitoring/health` avec `X-Monitoring-Token` | — |
| Recherche et analyse | **OpenSearch** | un document JSON par événement, dans un index daté | audit, alertes |
| Messagerie et stockage | **RabbitMQ** | un message par événement, sur un exchange, clé de routage par type | audit, alertes |
| Messagerie et stockage | **MinIO** (ou tout stockage S3) | un objet JSON par événement, archive à long terme | audit, alertes |
| Secrets | **HashiCorp Vault** | coffre externe : les mots de passe de BornToShare peuvent y rester | — |

Autorités privées (TLS « fichier ») : déposer le certificat de l'autorité dans `capsule-runner/certs/`, monté dans
core-service sous `/etc/b2s/certs` :

| Fichier | Extension |
|---|---|
| `opensearch-ca.pem` | OpenSearch |
| `rabbitmq-ca.pem` | RabbitMQ |
| `minio-ca.pem` | MinIO / S3 |
| `vault-ca.pem` | Vault |

« Vérification TLS » : `public` (autorités du système), `file` (le fichier ci-dessus), `none` (laboratoire seulement).

## OpenSearch

| Champ | Exemple |
|---|---|
| URL | `https://opensearch.corp.local:9200` |
| Index | `borntoshare-{yyyy}.{MM}` (`{yyyy}`, `{MM}`, `{dd}` : date de l'événement, UTC) |
| Utilisateur / mot de passe | compte dédié, mot de passe dans le coffre |

Envoi : `POST /<index>/_doc`, authentification basique. Document : l'événement tel qu'envoyé à Syslog et Splunk
(`type` : `audit`, `alerts`, `alerts_resolved` ; `category`, acteur, cible, résultat…), plus `@timestamp`, `source`
(`borntoshare`) et `host`. Rôle minimal côté OpenSearch :
`create_doc` et `create_index` sur `borntoshare-*`.

## RabbitMQ

| Champ | Exemple |
|---|---|
| URL de l'API de gestion | `https://rabbitmq.corp.local:15671` |
| Virtual host / exchange | `/` / `b2s.events` (exchange `topic` créé d'avance) |
| Préfixe de routage | `borntoshare` → clés `<préfixe>.<type>.<catégorie>` : `borntoshare.audit.access`, `borntoshare.alerts.governance`… |
| Utilisateur / mot de passe | compte dédié, droit `write` sur l'exchange seulement |

Envoi par l'API HTTP de gestion (`POST /api/exchanges/<vhost>/<exchange>/publish`, persistant, `application/json`).
Un message qu'aucune file ne reçoit est un **échec** (« non routé ») : lier au moins une file, par exemple `borntoshare.#`.

## MinIO (S3)

| Champ | Exemple |
|---|---|
| Point d'accès | `https://minio.corp.local:9000` |
| Bucket / préfixe | `b2s-audit` / `borntoshare` |
| Région | `us-east-1` (MinIO l'ignore) |
| Access key / secret key | clé dédiée ; la secret key dans le coffre |

Un objet par événement : `<préfixe>/<type>/AAAA/MM/JJ/HHMMSS-<id>.json`, en `PUT` signé AWS SigV4 (chemin, pas de
sous-domaine). Politique minimale : `s3:PutObject` sur `arn:aws:s3:::b2s-audit/borntoshare/*`. Pour une archive
inaltérable, activer le verrouillage d'objets (Object Lock) sur le bucket.

## HashiCorp Vault

Vault n'envoie rien : il **garde** des mots de passe à la place de BornToShare. Tout champ de mot de passe (annuaire,
serveur de fichiers, SMTP, secret d'une autre extension) accepte une référence :

```text
vault://<montage KV>/<chemin>#<clé>        par exemple  vault://secret/borntoshare/svc-b2s-sync#password
```

La référence est rangée chiffrée dans le coffre interne comme un mot de passe ; au moment de s'en servir, core-service
la lit dans Vault (KV version 2), la garde 60 s en mémoire au plus, ne l'écrit jamais. Changer le mot de passe dans
Vault suffit : il est pris au plus tard une minute après.

| Champ | Exemple |
|---|---|
| URL | `https://vault.corp.local:8200` |
| Authentification | `token`, ou `approle` (recommandé) |
| AppRole | role_id dans le champ, **secret_id** comme secret de l'extension ; montage `approle` |
| Namespace | Vault Enterprise seulement |
| Référence de test | `vault://secret/borntoshare/test#value` (lue par « Tester ») |

« Tester » vérifie : Vault joignable et descellé, identité acceptée (politiques affichées), référence de test lisible.
Politique minimale :

```hcl
path "secret/data/borntoshare/*" { capabilities = ["read"] }
```

Erreurs : une référence illisible (absente, refusée par la politique, Vault injoignable) fait échouer l'action qui en
avait besoin avec « Secret illisible : … », visible dans le journal des envois ou le test ; rien ne repart d'une valeur
ancienne. Le secret de l'extension Vault elle-même ne peut pas être une référence Vault.

## Essais en laboratoire

Recette du 2026-11-17 sur l'hôte de build, conteneurs de laboratoire sur le réseau `b2s-app` :

| Connecteur | Serveur de test | Résultat |
|---|---|---|
| OpenSearch | OpenSearch 2.x | documents indexés dans `borntoshare-AAAA.MM` |
| RabbitMQ | RabbitMQ 4 (management) | messages dans la file liée à `borntoshare.#` ; « non routé » sans file |
| MinIO | SeaweedFS (API S3) : les images MinIO n'étaient pas téléchargeables | objets écrits, signature SigV4 acceptée |
| Vault | Vault 1.20 (KV v2) | test OK, mot de passe RabbitMQ lu dans Vault ; référence absente → « Secret illisible » |

Tests unitaires : `core-service/app/tests/test_extensions_connectors.py`.
