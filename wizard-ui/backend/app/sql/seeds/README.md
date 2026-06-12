# Seeds (Wizard)

Ce dossier contient des **seeds DEV/TEST uniquement**.

- En mode **DEV** (`WIZARD_MODE=dev`), le wizard peut exécuter ces fichiers.
- En mode **PROD**, le seed est **interdit** (backend) et masqué côté UI.

## Contrainte importante

Les seeds doivent rester **compatibles avec le schéma SQL canonique** exécuté par le runner Wizard :

- [`services/wizard-ui/backend/app/sql/schema`](services/wizard-ui/backend/app/sql/schema)
- [`services/wizard-ui/backend/app/sql/views`](services/wizard-ui/backend/app/sql/views)
- [`services/wizard-ui/backend/app/sql/logging/schema`](services/wizard-ui/backend/app/sql/logging/schema)

La BDD est l’unique source de vérité. Les services ne doivent pas reconstruire le schéma au runtime.

## Seed standard

Le seed public standard est volontairement minimal : les fichiers SQL restent présents
pour garder `apply_seed=true` idempotent, mais ils n'insèrent plus de jeux de
démo riches par défaut.

- `040_seed_demo_full.sql`

Les anciens jeux demo publics sont conserves comme no-op dans les fichiers
numerotes `050` a `073`.

## Seeds privés (non publiés)

Si tu veux un seed "gros volume" **personnel** (non publié sur GitHub) :

1) place tes fichiers `.sql` dans : `backend/app/sql/seeds_private/`
2) assure-toi que `WIZARD_PRIVATE_SEEDS_DIR=seeds_private` (voir [`services/wizard-ui/.env.example`](services/wizard-ui/.env.example:1))
3) en mode DEV, cocher "Données de démonstration" déclenchera aussi ces seeds privés.

Ce dossier est ignoré par git via [`.gitignore`](services/wizard-ui/.gitignore:1).

### Bonnes pratiques

- Ne pas insérer de données sensibles (identités réelles, mots de passe, chemins/hosts internes).
- Éviter d’insérer des IDs explicites quand les tables utilisent `AUTO_INCREMENT`.
  Utiliser plutôt des colonnes uniques (`code`, etc.) + `INSERT IGNORE`.
