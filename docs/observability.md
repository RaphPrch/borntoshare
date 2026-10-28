# Observabilité

Menu **Observabilité** (`/observability`, administrateurs de la plateforme) : un seul endroit pour savoir
si tout va bien. Remplace les anciennes pages Événements, Tâches et Alertes (les anciennes adresses
redirigent vers l'onglet correspondant).

La période (24 h, 7 jours, 30 jours) s'applique à la vue d'ensemble et aux événements.

| Onglet | Contenu |
|---|---|
| Vue d'ensemble | état global, 4 indicateurs cliquables (alertes critiques, tâches en échec ou bloquées, composants en panne, connexions refusées), alertes à traiter regroupées par type, activité récente, tâches, santé par famille |
| Alertes | alertes ouvertes, filtres par gravité, type et zone, regroupement par type, acquitter / résoudre |
| Événements | journal d'audit paginé côté serveur, filtres module, résultat, gravité, acteur, recherche ; export CSV |
| Tâches | tâches du worker avec libellés lisibles, filtres statut et type, tâches bloquées (en file depuis plus de 5 min), arrêt, export CSV |
| Santé | composants surveillés et lancement du health check (configuration dans Paramètres avancés › Infrastructure) |

La barre du haut affiche deux pastilles : **Demandes** (demandes d'accès en attente) et **Alertes**
(alertes critiques ou hautes ouvertes, ouvre l'onglet Alertes filtré).

API (core-service) : `GET /observability/overview?period=`, `GET /observability/badge`, `GET /activity/search`.
