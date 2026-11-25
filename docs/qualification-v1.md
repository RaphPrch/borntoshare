# Qualification V1 : suivi

Mission de stabilisation et de qualification de la V1 (BornToShare et module 5S). Branche
`stabilization/v1-qualification` dans chaque dépôt ; les branches principales (`main`, `master`) ne sont pas
modifiées. Point de départ : tag local `v1-baseline` (borntoshare c347768, b2s-fives-module 69569da).

Tests : `make test` (ou `testing/run-tests.sh`), chaque suite dans l'image de son service ; `FIVES_REPO=<dépôt du
module>` ajoute les suites du 5S. Installation : `testing/install-lab/lab.sh run <scénario>`.

| Lot | Contenu | Commit | Tests | Résultat | Problèmes connus | Retour arrière |
|---|---|---|---|---|---|---|
| 0 | Audit initial ; lanceur unique des tests ; 3 erreurs Ruff de `main` corrigées ; faux échec du labo (`grep -q` sous `pipefail`) | voir `git log` | toutes les suites | lint OK ; core 558 ; auth 74 ; capsule 161 ; wizard 37 ; interface 23 scripts + check ; fives-service 57 ; fives-scanner 53 | — | `git revert` du commit |

## État initial (audit)

Anomalies retenues, par gravité (détail : rapport d'audit) :

| # | Gravité | Anomalie | Lot |
|---|---|---|---|
| C1 | CRITICAL | Sauvegarde sans la clé `b2s_master_key`, ni `.env`, ni secrets ; pas de restauration, jamais testée | 1, 8 |
| H1 | HIGH | Suppression d'un annuaire : un comptage de dépendance en échec est ignoré | 1 |
| H2 | HIGH | ACL : timeout déclaré échec sans relecture ; pas de contrôle avant écriture | 1 |
| H3 | HIGH | Job RUNNING abandonné par un worker mort jamais clôturé ; watchdog muet sur ses erreurs | 4 |
| H4 | HIGH | Jeton interne unique, identité déclarée par l'appelant | décision d'architecture |
| H5 | HIGH | `fives-service` arrêté sur le build | 6 |
| M1 | MEDIUM | Exceptions avalées qui transforment une erreur en résultat vide | 2 |
| M2 | MEDIUM | Logs non JSON, champs communs non garantis | 3 |
| M3 | MEDIUM | Pas de sonde de vie distincte de la disponibilité | 5 |
| M4 | MEDIUM | Tests du 5S liés à un emplacement non documenté, pas de lanceur unique | 0 |
| M5 | MEDIUM | Installation hors ligne impossible | limite documentée |

## Lot suivant

Lot 1 : C1 (sauvegarde complète, `make restore`, essai au labo), H1, H2.
