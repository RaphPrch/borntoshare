# Qualification V1 : suivi

Mission de stabilisation et de qualification de la V1 (BornToShare et module 5S). Branche
`stabilization/v1-qualification` dans chaque dépôt ; les branches principales (`main`, `master`) ne sont pas
modifiées. Point de départ : tag local `v1-baseline` (borntoshare c347768, b2s-fives-module 69569da).

Tests : `make test` (ou `testing/run-tests.sh`), chaque suite dans l'image de son service ; `FIVES_REPO=<dépôt du
module>` ajoute les suites du 5S. Installation : `testing/install-lab/lab.sh run <scénario>`.

| Lot | Contenu | Commit | Tests | Résultat | Problèmes connus | Retour arrière |
|---|---|---|---|---|---|---|
| 0 | Audit initial ; lanceur unique des tests ; 3 erreurs Ruff de `main` corrigées ; faux échec du labo (`grep -q` sous `pipefail`) | e38ddb1 | toutes les suites | lint OK ; core 558 ; auth 74 ; capsule 161 ; wizard 37 ; interface 23 scripts + check ; fives-service 57 ; fives-scanner 53 | — | `git revert` du commit |
| 1 | C1 sauvegarde complète (clé, secrets, `.env`, certificats, manifeste) et `make restore` ; H1 suppression d'annuaire fermée en cas d'erreur ; H2 ACL relue après timeout, pas de réécriture d'une ACE présente | 029ce9d | core, capsule, lint, labo `restore` | core 560 ; capsule 167 ; labo restore 39/39 | sauvegarde du certificat HTTPS de l'interface hors périmètre (fourni par le client) | `git revert` ; une sauvegarde de l'ancien format reste restaurable à la main (docs) |
| 2 | M1 exceptions avalées à impact : journalisées avec code et contexte, comportement dégradé inchangé | 21011ee | core | 3 tests ; core complet 572 avec les lots 1 à 5 | absence de mesures 5S non signalée à l'écran (journal seulement) : plus tard | `git revert` |
| 3 | M2 formateur commun texte / JSON (`LOG_FORMAT`), champs `extra=` enfin écrits, secrets masqués | e4dce2a | core, auth, capsule | 5 tests ; services sains au labo avec ce formateur | journaux d'accès d'uvicorn inchangés (texte) | `git revert` ; `LOG_FORMAT=text` par défaut |
| 4 | H3 jobs RUNNING abandonnés clôturés `JOB_ABANDONED` ; watchdog journalisé ; contrat des temps limites vérifié des deux côtés | 78f3b2b | core | 3 tests ; core 572 | essai « worker tué » au labo non fait (délai minimal 25 min) | `git revert` ; `JOB_WATCHDOG_RUNNING_GRACE_SECONDS` |
| 5 | M3 `/health/live` (sans dépendance) dans core, auth, worker ; `/health` reste la disponibilité ; docs exploitation (journaux, santé, jobs) | cb8dd16 | core, auth, capsule | core 572 ; auth 75 ; capsule 168 ; wizard 38 ; lint OK | les healthchecks des conteneurs restent sur `/health` (voulu : ordre de démarrage) | `git revert` |
| 6 | Recette réelle AD / SMB / NTFS sur le build avec cette branche. Deux défauts trouvés et corrigés : déclaration d'un serveur de fichiers bloquée par la résolution DNS en série des serveurs déclarés (283 s, l'interface abandonne à 120 s) ; instantané d'annuaire perdu sur deadlock MariaDB quand deux annuaires sont synchronisés en même temps. H5 : `fives-service` relancé, doublon `services_fives-scanner_1` retiré | 59ba0fe, 8623bd0 | `e2e_check.py` (64 contrôles) ; core | e2e 56/64 avant, **64/64** après (1 SKIP connu : GG_B2S_Admins sans rôle) ; core 577 | le rejeu sur deadlock n'a pas été déclenché pendant la recette (prouvé par ses tests) ; un instantané resté QUEUED bloque sa source 30 min (garde existante) | `git revert` |
| 7 | Dépendances : pip-audit (6 services, 0 vulnérabilité), npm audit production 0 ; `@sveltejs/kit` 2.70.4 : avis non exploitables ici (pas de remote functions ni de prérendu ; redirection du formulaire de connexion déjà filtrée par `safeInternalPath`) → montée en version 3 plus tard. Sauvegarde chiffrée : `.env` et certificats aussi (ils restaient en clair), `openssl` contrôlé avant le dump. Temps de réponse mesurés (`testing/perf/api_timings.py`) | 08cf636 | toutes les suites ; labo `restore` | toutes les suites vertes ; restore 41/41 ; médiane ≤ 90 ms sauf `/storage-roots/context` 672 ms (2 125 dossiers) | — | `git revert` |
| 8-9 | Documentation d'exploitation (mettre à jour, dépannage) ; labo : nettoyage garanti d'une exécution interrompue (hôtes, mots de passe, clé SSH) ; campagne finale | voir `git log` | labo complet | containers 37/37 ; hybrid 44/44 ; native 35/35 ; faults 41/41 ; restore 41/41 ; e2e AD 64/64 | faults a d'abord échoué faute de place sur le build (1,3 Go) : 41/41 après nettoyage des volumes anonymes ; mise à jour entre versions et volumétrie 5S non testées | `git revert` |
| P4 | Centre de diagnostic (18 contrôles : résultat, gravité, explication, marche à suivre, export CSV) ; dernière erreur d'un composant revenu | 487e3d9 | core, interface | core 585 ; interface 24 + check ; écran vérifié sur le build (fr, en) | — | `git revert` |
| P5 | Job Center : worker de chaque job (contrat start, champ optionnel des deux côtés), export de diagnostic d'un job, métriques et erreur masquées | f01f63c | core, capsule, interface | core 588 ; capsule 168 ; interface 25 + check ; vérifié sur le build | progression : affichée pour les mesures 5S (sous-dossiers faits / total, fichiers, déjà en place) ; aucune pour les jobs du worker, qui n'en remontent pas | `git revert` |
| P7 | Simulation ACL avant validation : ACL actuelle, changement exact, risques, confirmation quand il y a des risques | 333ec2c | core, interface | core 593 ; interface 25 + check ; deux demandes réelles du labo AD sur le build | la comparaison porte sur la dernière lecture de l'ACL (son âge est affiché, ancienne au-delà de 7 jours) | `git revert` |
| P12 | Aperçu d'un dossier : « permissions indisponibles » au lieu d'un chargement sans fin ; revue des erreurs avalées et des actions sensibles (déjà confirmées ou annulables) | voir `git log` | interface | 25 + check | cas d'échec non reproduit en réel | `git revert` |
| N3 | Deux déclarations simultanées du même serveur de fichiers passaient toutes les deux (doublon « AD lab file server » sur le build) : verrou nommé MariaDB autour du contrôle et de l'insertion (`app/services/named_lock.py`) | voir `git log` | core ; essai réel | core 595 ; sur le build, deux déclarations simultanées : 200 et 409, un seul serveur | changement d'adresse aussi sous ce verrou, avec une lecture verrouillante (REPEATABLE READ) : 3 essais réels de chaque cas, 200 et 409, un seul serveur | `git revert` |
| H4 | Jeton par service vers core-service (`X-Service-Token`), droits fixés par le core (routes du worker et du module 5S, portées), identité signée (`X-B2S-Actor`, clé du cookie principal) par le BFF et auth-service, relayée par le module 5S ; mode d'avant tant que `make deploy` n'a pas créé les jetons ; contrôle « Identité des services » du diagnostic | voir `git log` | core, auth, capsule, interface, module 5S ; tentatives réelles ; e2e AD | core 605 ; auth 77 ; capsule 169 ; interface 27 + check ; 5S 59 + 53 ; usurpations depuis le worker, le module 5S et l'interface refusées (403) ; e2e AD 64/64 en mode par service | appels vers auth-service, le worker et le module 5S encore au jeton partagé ; labo hybride et natif à repasser | `git revert` ; sans les jetons, le mode d'avant |

Statut : **READY WITH LIMITATIONS** (rapport de qualification).

## État initial (audit)

Anomalies retenues, par gravité (détail : rapport d'audit) :

| # | Gravité | Anomalie | Lot |
|---|---|---|---|
| C1 | CRITICAL | Sauvegarde sans la clé `b2s_master_key`, ni `.env`, ni secrets ; pas de restauration, jamais testée | 1, 8 |
| H1 | HIGH | Suppression d'un annuaire : un comptage de dépendance en échec est ignoré | 1 |
| H2 | HIGH | ACL : timeout déclaré échec sans relecture ; pas de contrôle avant écriture | 1 |
| H3 | HIGH | Job RUNNING abandonné par un worker mort jamais clôturé ; watchdog muet sur ses erreurs | 4 |
| H4 | HIGH | Jeton interne unique, identité déclarée par l'appelant | fait (accord du 25/11) |
| H5 | HIGH | `fives-service` absent sur le build (conteneur disparu après le déploiement du 17/11) : relancé, le core le joint | 6 (fait) |
| M1 | MEDIUM | Exceptions avalées qui transforment une erreur en résultat vide | 2 |
| M2 | MEDIUM | Logs non JSON, champs communs non garantis | 3 |
| M3 | LOW | Pas de sonde de vie distincte (revu : podman ne redémarre pas un conteneur « unhealthy », pas de redémarrage en boucle) | 5 |
| M4 | MEDIUM | Tests du 5S liés à un emplacement non documenté, pas de lanceur unique | 0 |
| M5 | MEDIUM | Installation hors ligne impossible | limite documentée |

## Constats en cours

- Espace disque du build : `/` à 99 % pendant la campagne (volumes anonymes de conteneurs supprimés, images de
  rollback) ; deux exécutions du labo ont échoué faute de place ; 90 % après nettoyage.
- `@sveltejs/kit` (dépendance de construction, embarquée dans l'interface) : 4 avis npm dont un « high » ; le
  correctif est une version majeure (lot 7).

## Décision prise

H4 : fait le 25/11 (jeton par service vers core-service, identité signée).
