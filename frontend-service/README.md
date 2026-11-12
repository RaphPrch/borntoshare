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

Pages principales : tableau de bord, Dossiers (fiche, permissions, sensibilité, demande rapide en panneau),
Demandes (liste, et création sur une seule page avec résumé en direct et suggestions de dossiers), Observabilité,
Rapports, Carte d'exposition, 5S (partages, explorateur, doublons, rapport, scanner), Serveurs (serveurs de fichiers
et espaces de noms DFS), Zones, Annuaires, Identités, Tags, Réglages avancés ; `/setup` pour le premier démarrage.

## Variables

`INTERNAL_TOKEN`, `PRINCIPAL_SIGNING_KEY` (obligatoire en production), `ORIGIN` (`FRONTEND_PUBLIC_ORIGIN`), `B2S_AUTH_URL`,
`B2S_CORE_URL` ; au build, `B2S_VERSION` (version affichée dans le menu, fournie par `make deploy`).

## Développement

```bash
npm ci
npm run check                 # svelte-check : aucune nouvelle erreur
npm run test:error-normalize  # tests unitaires : npm run test:<nom> (voir package.json)
```
