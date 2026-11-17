# Revues des accès

Governance › Access Management › **Revues** (`/access-reviews`). Une campagne fait vérifier, à un moment donné, chaque
accès aux dossiers gouvernés par leurs gardiens ; la revue close est la preuve du contrôle (ISO 27001, NIS2).

## Déroulement

1. **Ouverture** (administrateur) : un nom, une date de fin, tous les dossiers gouvernés ou certains. Chaque personne
   qui accède à chaque dossier à cet instant est listée, avec son niveau et ses chemins d'accès (demande, groupe AD
   de BornToShare, groupe hors BornToShare, groupe imbriqué), tels que les calcule l'onglet Permissions du dossier.
   Les gardiens sont prévenus (cloche, et e-mail si les notifications sont activées).
2. **Revue** (gardiens, et administrateurs) : pour chaque personne, **Garder** ou **Retirer** ; « Garder tous les
   autres » pour finir un dossier. Un gardien ne voit que ses dossiers.
3. **Retraits** : « Appliquer les retraits » révoque les accès accordés par une demande, par le chemin habituel
   (la personne sort du groupe AD du dossier, la demande passe à révoquée). Un accès que BornToShare n'a pas accordé
   (groupe hors BornToShare, droit posé à la main) est marqué « à retirer à la main », avec le groupe à quitter.
4. **Clôture** (administrateur) : la revue ne change plus ; « Exporter la preuve » donne le CSV de chaque décision
   (qui, quand, résultat). Les accès non revus restent tels quels et l'export le dit.

Chaque ouverture, décision, application et clôture est dans le journal d'audit chaîné (`access_review.*`).

À l'écran :

- **La liste** : une carte par revue (avancement gardés / à retirer / à revoir, échéance colorée : à moins de 7 jours,
  en retard), les chiffres des revues en cours (accès à revoir, échéance la plus proche, retraits à appliquer). On ouvre
  une revue dans un panneau latéral : périmètre (tous les dossiers, ou une sélection par nom, zone ou serveur),
  échéance en un clic (2 semaines, 3 semaines, 1 mois) ou une date.
- **Décider** : à gauche les dossiers de la revue et ce qui reste à décider dans chacun ; au centre une carte par
  personne (niveau, chemin d'accès, accès accordé hors BornToShare), **Garder** / **Retirer** en un clic. Clavier :
  ↑ ↓ choisir, G garder, R retirer, → ← dossier suivant ou précédent, Z annuler ; clic droit pour toutes les actions.
  Une décision met la ligne à jour sur place : la revue n'est pas relue en entier.
- **Bilan et application** : retraits automatiques, retraits à la main, accès encore à décider ; la liste des retraits
  avec la façon de les faire et leur résultat ; « Appliquer les retraits » ; la clôture (administrateurs).

## Technique

- Tables `access_reviews` et `access_review_items` (paquet `164_access_reviews.sql`).
- Routes `GET|POST /access-reviews`, `GET /access-reviews/{id}`, `POST /access-reviews/{id}/decisions`,
  `POST /access-reviews/{id}/close` (core-service) ; `POST /governance/access-reviews/{id}/apply` (orchestration :
  révocations).
