# Seeds (Wizard)

Ce dossier contient des **seeds DEV/TEST uniquement**.

- En mode **DEV** (`WIZARD_MODE=dev`), le wizard peut exécuter ces fichiers.
- En mode **PROD**, le seed est **interdit** (backend) et masqué côté UI.

## Contrainte importante

Les seeds doivent rester **compatibles avec le schéma** défini dans [`backend/app/sql/schema/001_schema.sql`](services/wizard-ui/backend/app/sql/schema/001_schema.sql:1).

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

