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
| 5 | M3 `/health/live` (sans dépendance) dans core, auth, worker ; `/health` reste la disponibilité ; docs exploitation (journaux, santé, jobs) | voir `git log` | core, auth, capsule | core 572 ; auth 75 ; capsule 168 ; wizard 38 ; lint OK | les healthchecks des conteneurs restent sur `/health` (voulu : ordre de démarrage) | `git revert` |

## État initial (audit)

Anomalies retenues, par gravité (détail : rapport d'audit) :

| # | Gravité | Anomalie | Lot |
|---|---|---|---|
| C1 | CRITICAL | Sauvegarde sans la clé `b2s_master_key`, ni `.env`, ni secrets ; pas de restauration, jamais testée | 1, 8 |
| H1 | HIGH | Suppression d'un annuaire : un comptage de dépendance en échec est ignoré | 1 |
| H2 | HIGH | ACL : timeout déclaré échec sans relecture ; pas de contrôle avant écriture | 1 |
| H3 | HIGH | Job RUNNING abandonné par un worker mort jamais clôturé ; watchdog muet sur ses erreurs | 4 |
| H4 | HIGH | Jeton interne unique, identité déclarée par l'appelant | décision d'architecture |
| H5 | HIGH | `fives-service` absent sur le build (conteneur disparu après le déploiement du 17/11) : relancé, le core le joint | 6 (fait) |
| M1 | MEDIUM | Exceptions avalées qui transforment une erreur en résultat vide | 2 |
| M2 | MEDIUM | Logs non JSON, champs communs non garantis | 3 |
| M3 | LOW | Pas de sonde de vie distincte (revu : podman ne redémarre pas un conteneur « unhealthy », pas de redémarrage en boucle) | 5 |
| M4 | MEDIUM | Tests du 5S liés à un emplacement non documenté, pas de lanceur unique | 0 |
| M5 | MEDIUM | Installation hors ligne impossible | limite documentée |

## Constats en cours

- Espace disque du build : `/` à 96 % (images de rollback, cache) ; le labo a échoué une fois faute de place.
- `@sveltejs/kit` (dépendance de construction, embarquée dans l'interface) : 4 avis npm dont un « high » ; le
  correctif est une version majeure (lot 7).

## Lot suivant

Lot 6 : intégration réelle AD / SMB / NTFS (`testing/ad-lab`) sur le build, avec le code de cette branche.
