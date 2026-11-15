# Governance Jobs (observabilité)

Menu **Governance › Governance Jobs** (`/observability`) : un seul endroit pour savoir si tout va bien.
Les administrateurs de la plateforme voient tout ; un gardien est renvoyé vers `/observability/mine`
(ses actions, ses demandes, les dossiers qu'il garde).

La période (24 h, 7 jours, 30 jours) s'applique à la vue d'ensemble et aux événements.

| Onglet | Contenu |
|---|---|
| Vue d'ensemble | état global, indicateurs cliquables (alertes critiques, tâches en échec ou bloquées, composants en panne, connexions refusées), alertes à traiter regroupées par type, activité récente, tâches, santé par famille |
| Alertes | alertes ouvertes, filtres par gravité, type et zone, regroupement par type, acquitter / résoudre |
| Événements | journal d'audit paginé côté serveur, filtres module, résultat, gravité, acteur, recherche ; export CSV |
| Jobs | tâches du worker avec libellés lisibles, filtres statut et type, tâches bloquées (en file depuis plus de 5 min) ; clic droit sur une tâche : détails, cible, relancer, arrêter, copier l'identifiant ; export CSV |
| Santé | composants surveillés et lancement du health check (configuration dans Administration › Settings › Infrastructure) |

Dans le menu latéral, l'entrée Governance Jobs porte le nombre d'alertes critiques ouvertes (administrateurs).
La cloche de la barre du haut ouvre le centre de notifications (voir [notifications.md](notifications.md)).

API (core-service) : `GET /observability/overview?period=`, `GET /observability/badge`, `GET /activity/search`,
`GET /activity/mine`.
