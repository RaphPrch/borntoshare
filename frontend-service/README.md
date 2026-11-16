# frontend-service

L'interface de BornToShare et son BFF (Backend For Frontend). C'est la seule entrée publique : le navigateur ne
parle qu'à lui, et lui seul appelle auth-service et core-service, en ajoutant le jeton interne et l'identité de
l'utilisateur.

| | |
|---|---|
| Image | `b2s-frontend-service` (SvelteKit, adapter-node, Node 26), utilisateur 10006 |
| Port | 3000, **publié** (`FRONTEND_PUBLISHED_PORT`) ; à placer derrière un proxy HTTPS |
| Appelle | auth-service (`B2S_AUTH_URL`), core-service (`B2S_CORE_URL`) |
| Santé | `GET /login` |

## Comment une requête passe

1. Le navigateur appelle `/api/<ressource>` avec ses cookies.
2. `src/hooks.server.ts` vérifie la session (cookie `b2s_principal` signé) et l'origine (`ORIGIN`).
3. `src/lib/server/bff/` choisit le service (`service-routes.ts`) et relaie la requête avec `X-Internal-Token`
   et l'identité de l'utilisateur.
4. La réponse revient dans une enveloppe commune ; une erreur du service est rendue avec son code métier.

## Organisation

Voir [docs/structure.md](docs/structure.md) (dossiers de `src/lib`) et [docs/ui-conventions.md](docs/ui-conventions.md)
(composants communs, erreurs, traductions).

## Écrans

Pas de menu latéral : la barre du haut (`AppHeader`) porte le bouton ☰, qui ouvre le menu en quatre sections
(`src/lib/components/layout/nav.ts`, chaque entrée avec ses pages et les pages récentes), la recherche ⌘K, les tâches en
cours, la cloche et le compte. Dessous, la barre de contexte (`ContextBar`) donne le fil d'Ariane et les onglets de
l'entrée ; en bas, les tâches récentes (`RecentTasks`, administrateurs). Les pages prennent toute la largeur ; leurs
panneaux collants partent de `--b2s-shell-top`.
Les noms du menu sont des noms de produit, en anglais dans les deux langues.

| Section | Entrée | Pages |
|---|---|---|
| Workspace | Dashboard (`/dashboard`) | Journal du jour : titre, « À la une », fil du jour, carte des dossiers, question à Pilot |
| | Pilot (`/pilot`, administrateurs et gardiens) | questions en français sur les dossiers (« exporte-moi tous les utilisateurs du dossier TEST »), réponses en liste, export CSV, copie, historique |
| Governance | Storage Roots (`/storage-roots`) | liste (filtres, tri, actions groupées, aperçu latéral), fiche du dossier en onglets : vue d'ensemble, permissions, stockage · 5S, sensibilité, quota, activité |
| | Access Management (`/access-requests`) | onglets Demandes, Exposition (`/exposure`) et Revues (`/access-reviews` : campagnes de revue des accès) |
| | Governance Jobs (`/observability`) | vue d'ensemble, alertes, événements, jobs, santé |
| | Policies (`/admin/policies`, administrateurs) | automatismes de gouvernance : tags, alertes, scans sur une règle |
| Storage Intelligence | Explorer (`/five-s/explore`) | recherche de fichiers dans tous les dossiers, puis la fiche d'un dossier en onglets : Contenu, Atelier 5S, Doublons, Droits à revoir, Rapport (module 5S, voir [docs/module-5s.md](../docs/module-5s.md)) |
| | Inventory (`/five-s/scanner`) | onglets Scans, Dossiers (état de chaque mesure : complète, partielle, échantillonnée), Quarantaine (copies et archives de tous les dossiers, restauration), Réglages |
| | Analytics (`/five-s`) | score 5S des dossiers et « Quoi faire d'abord » |
| | Insights & Recommendations (`/reports`) | rapports |
| Administration | Storage Endpoints (`/admin/storage-endpoints`) | onglets Serveurs (serveurs de fichiers, espaces DFS) et Zones |
| | Identity & Users (`/admin/identity`) | onglets Identités, Administrateurs, Annuaires |
| | Settings (`/admin/advanced-settings`) | onglets Réglages, en quatre groupes : Général (nommage, gouvernance), Sécurité (sessions, journalisation), Réseau et infrastructure (réseau et DNS, infrastructure, workers), Intégrations et licence (licence et modules, notifications, extensions) ; et Tags |

Les listes ont un menu au clic droit (dossiers, jobs, exposition, tags, politiques, identités). `/setup` sert au
premier démarrage. Interface pour poste de travail uniquement.

## Variables

`INTERNAL_TOKEN`, `PRINCIPAL_SIGNING_KEY` (obligatoire en production), `ORIGIN` (`FRONTEND_PUBLIC_ORIGIN`), `B2S_AUTH_URL`,
`B2S_CORE_URL` ; au build, `B2S_VERSION` (version affichée dans le menu, fournie par `make deploy`).

## Développement

```bash
npm ci
npm run check                 # svelte-check : aucune nouvelle erreur
npm run test:error-normalize  # tests unitaires : npm run test:<nom> (voir package.json)
```
