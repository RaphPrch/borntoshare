# BornToShare

BornToShare gouverne l'accès aux dossiers partagés Windows (SMB et DFS) à partir de l'Active Directory.
Un utilisateur demande un accès à un dossier, un gardien du dossier le valide, et BornToShare l'applique :
groupe AD créé dans l'OU de la zone, membre ajouté, ACL NTFS posée sur le dossier. À la fin de l'accès
ou à la révocation, le membre est retiré. Tout est tracé dans un journal d'audit chaîné.

Autour de ce cycle : la sensibilité des dossiers (secrets et données personnelles, et qui peut les ouvrir), la carte
d'exposition, des politiques automatiques, des e-mails aux gardiens et aux demandeurs, et, sous licence, le module 5S
qui mesure et range les partages. Chaque compte de service n'a que les droits dont il a besoin.

## Vue d'ensemble

```mermaid
flowchart LR
  user([Navigateur]) -- HTTPS 3000 --> front[frontend-service<br/>interface + BFF]
  front --> auth[auth-service<br/>connexion, sessions]
  front --> core[core-service<br/>API, gouvernance, planificateur]
  core -- travaux --> redis[(Redis)]
  redis --> worker[capsule-runner<br/>actions AD, SMB, DFS]
  worker -- API interne --> core
  core --> db[(MariaDB<br/>borntoshare + borntoshare_logging)]
  auth --> redis
  worker -- LDAPS, Kerberos, SMB, WinRM, DNS --> ad[[Active Directory<br/>serveurs de fichiers, DFS]]
  auth -- LDAPS --> ad
  front --> fives[fives-service<br/>module 5S]
  fives --> core
  scanner[fives-scanner] -- WinRM --> ad
  scanner --> core
  core -- SMTP --> mail[[Serveur SMTP]]
```

| Conteneur | Rôle | Documentation |
|---|---|---|
| frontend-service | Interface SvelteKit et BFF (seule entrée publique) | [frontend-service/README.md](frontend-service/README.md) |
| auth-service | Connexion (comptes locaux, AD, SSO Keycloak), sessions | [auth-service/README.md](auth-service/README.md) |
| core-service | Données, gouvernance, audit, coffre des secrets, planificateur | [core-service/README.md](core-service/README.md) |
| capsule-runner | Worker : toutes les actions sur l'AD et les serveurs | [capsule-runner/README.md](capsule-runner/README.md) |
| redis | File des travaux et sessions | [docs/architecture.md](docs/architecture.md) |
| wizard-ui | Installation (bases, administrateur, licence, module 5S), une seule fois | [wizard-ui/README.md](wizard-ui/README.md) |
| fives-service, fives-scanner | Module 5S, sous licence : mesures, doublons, archives, scores | [docs/module-5s.md](docs/module-5s.md) |
| mailpit | Laboratoire seulement : serveur SMTP de test (`make mail-up`) | [docs/notifications.md](docs/notifications.md) |

## Démarrer

1. Préparer une base MariaDB et un hôte Linux avec Podman : [docs/installation.md](docs/installation.md).
2. `cp .env.example .env && chmod 600 .env`, puis renseigner chaque valeur.
3. `make wizard` : le wizard crée les bases, le compte SQL de l'application et le premier administrateur.
4. `make wizard-down`, puis `make up` : l'application répond sur `FRONTEND_PUBLIC_ORIGIN`.
5. À la première connexion, l'assistant de premier démarrage (`/setup`) déclare l'annuaire, le premier serveur
   de fichiers et les premiers dossiers.

Mises à jour : `make deploy` (paquets SQL, point de retour, reconstruction). Voir [docs/installation.md](docs/installation.md).

## Documentation

| Sujet | Fichier |
|---|---|
| Architecture, réseaux, flux à ouvrir | [docs/architecture.md](docs/architecture.md) |
| Installation, `.env`, wizard, mises à jour, sauvegarde | [docs/installation.md](docs/installation.md) |
| Sécurité : jetons, secrets, protocoles, conteneurs | [docs/securite.md](docs/securite.md) |
| **Droits minimums des comptes dans l'AD et sur les serveurs** | [docs/droits-ad.md](docs/droits-ad.md) |
| Provisionnement AD (groupes, OU, adoption, aperçu d'approbation) | [docs/provisionnement-ad.md](docs/provisionnement-ad.md) |
| Sensibilité des dossiers et carte d'exposition | [docs/sensibilite.md](docs/sensibilite.md) |
| Notifications par e-mail (SMTP, Gmail, Mailpit) | [docs/notifications.md](docs/notifications.md) |
| Module 5S | [docs/module-5s.md](docs/module-5s.md) |
| Infrastructure : santé, planifications, workers, serveur injoignable | [docs/infrastructure.md](docs/infrastructure.md) |
| SSO Keycloak | [docs/keycloak.md](docs/keycloak.md) |
| Observabilité | [docs/observability.md](docs/observability.md) |
| Pilote sur un AD Windows | [docs/pilote-windows.md](docs/pilote-windows.md) |
| AD de test et tests de bout en bout | [docs/ad-lab.md](docs/ad-lab.md) |
| Règles de travail sur le code | [Agents.md](Agents.md) |

## Commandes

```text
make up | down | restart | ps | logs | logs-<service>
make deploy            mise à jour : paquets SQL, point de retour, reconstruction (FORCE=1 pendant une mesure 5S)
make backup            sauvegarde des deux bases dans backups/ (pas la clé des secrets)
make wizard            wizard d'initialisation ; make wizard-down pour l'arrêter
make ad-lab-up         AD de test pour les tests de bout en bout (jamais en production)
make mail-up           serveur de mails de test Mailpit, http://<hôte>:8025 (jamais en production)
make lint              contrôle du code Python des quatre services (Ruff, règles dans ruff.toml)
```

## Aperçu

| | |
|---|---|
| ![Tableau de bord](docs/screenshots/01-tableau-de-bord.png) Tableau de bord | ![Dossiers](docs/screenshots/02-dossiers.png) Dossiers : arborescence, mesure, demandes à traiter |
| ![Nouvelle demande](docs/screenshots/09-nouvelle-demande.png) Nouvelle demande : une page, résumé en direct, suggestions | ![Demandes d'accès](docs/screenshots/03-demandes-acces.png) Demandes d'accès |
| ![Sensibilité](docs/screenshots/sensibilite.png) Sensibilité : la cause, et qui peut ouvrir chaque fichier | ![Carte d'exposition](docs/screenshots/11-exposition.png) Carte d'exposition |
| ![5S](docs/screenshots/12-5s.png) 5S des partages | ![Explorateur 5S](docs/screenshots/5s-explorateur.png) Explorateur 5S |
| ![Suivi](docs/screenshots/06-observabilite.png) Suivi : alertes, tâches, activité | ![Santé](docs/screenshots/10-sante.png) Santé : annuaire, OU des groupes, serveurs |
| ![Serveurs](docs/screenshots/04-serveurs.png) Serveurs de fichiers | ![Zones](docs/screenshots/05-zones.png) Zones |
| ![Politiques](docs/screenshots/07-politiques.png) Politiques intelligentes | ![Connexion](docs/screenshots/08-connexion.png) Connexion |
| ![E-mail au gardien](docs/screenshots/mail-nouvelle-demande.png) E-mail « Nouvelle demande » | ![E-mail d'alerte](docs/screenshots/mail-alerte-sensibilite.png) E-mail « Fichiers ouverts à tous » |

Captures faites le 12 novembre 2026 sur l'instance de build, avec les données du laboratoire CORP.LOCAL.
