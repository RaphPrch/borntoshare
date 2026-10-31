# Infrastructure

Administration › Paramètres avancés › **Infrastructure** (administrateurs de la plateforme).
Cinq onglets : base de données, workers, Keycloak, planification, composants surveillés.
Keycloak est décrit dans [keycloak.md](keycloak.md). L'état de la plateforme se consulte dans
**Observabilité › Santé** (voir [observability.md](observability.md)).

## Santé (Observabilité)

État de chaque composant : opérationnel, dégradé (réponse en plus de 1,5 s ou partielle), en panne, inconnu
(aucun résultat depuis trois intervalles du health check). Chaque ligne montre les derniers contrôles,
la disponibilité sur 24 h et la latence. Les compteurs en haut filtrent la liste.

## Health check

Il tourne selon la fréquence de l'onglet Planification (5 min par défaut), en deux parties :

| Contrôlé par | Composants |
|---|---|
| core-service | base de données et base d'audit (requête SQL), file de tâches (Redis), chaque worker via son agent |
| un worker (tâche `INFRA_HEALTH`) | services de la plateforme, port de la base, contrôleurs de domaine des sources d'identité, serveurs de fichiers (port 445), Keycloak, composants ajoutés à la main |

Les sources d'identité AD sont contrôlées comme un annuaire, pas seulement par leur port : connexion LDAPS
(certificat vérifié selon le réglage de l'annuaire), bind avec le compte qui lit l'annuaire (compte « snapshot »,
sinon celui de la source) et lecture du DN de base. Un compte désactivé, expiré ou refusé, un certificat
invalide ou un DNS faux passent la source « en panne » avec la cause. Un mot de passe changé dans l'AD
reste accepté une heure par le contrôleur de domaine (comportement d'Active Directory).

Un worker ne peut pas signaler qu'il est en panne : c'est core-service qui interroge son agent.
L'historique est gardé 7 jours (`infra_check_history`).

## Data sync

Exécuté par les workers, 6 h par défaut. Trois parties, activables séparément :

1. **Snapshots** : chaque source AD active avec « Inventaire par snapshot ». Une source déjà en cours est sautée.
2. **Découverte des partages** : chaque serveur de fichiers SMB qui a un compte. Les racines trouvées ou non trouvées sont mises à jour.
3. **Dérive des ACL et des groupes** : lecture de l'ACL de chaque racine gouvernée, et comparaison des membres de chaque groupe AD
   (dernier snapshot) avec les demandes appliquées, ni révoquées ni expirées. Les écarts deviennent des alertes de gouvernance :
   - « accès accordé mais absent du groupe AD » (`ad_member_missing`)
   - « membre du groupe AD sans accès accordé » (`ad_member_not_granted`)
   - « groupe absent de l'ACL » et « ACL non gouvernée » (déjà existantes)

Le premier data sync a lieu un intervalle après l'installation, pas au premier démarrage.

## Secrets et sauvegarde

Les mots de passe des annuaires et des serveurs de fichiers sont chiffrés (AES-256-GCM) dans la table `secret_items` de la base.
core-service les chiffre et les déchiffre ; auth-service et les workers les lui demandent par une route interne, avec `INTERNAL_TOKEN`.
`B2S_SECRET_MASTER_KEY` reste dans `.env` et n'est jamais en base : un dump ou un accès SQL seul ne donne donc pas les mots de passe.
En revanche, une faille permettant d'exécuter du code dans core-service y donnerait accès, puisqu'il détient la clé et la base.

Une sauvegarde complète comprend **deux éléments** : la base et `B2S_SECRET_MASTER_KEY`, à conserver séparément. Sans la clé, les
références restent en base mais les annuaires passent en panne (« mot de passe illisible ») jusqu'à leur nouvelle saisie.

`make backup` enregistre les deux bases dans `backups/` (fichiers lisibles par leur seul propriétaire). La clé n'y est pas : à conserver
dans un coffre, à part. Pour restaurer sur une installation arrêtée, avec le même `.env` :

```bash
zcat backups/<date>/borntoshare.sql.gz | mariadb -h <hôte> -u <compte> -p borntoshare
zcat backups/<date>/borntoshare_logging.sql.gz | mariadb -h <hôte> -u <compte> -p borntoshare_logging
```

Puis relancer les services et vérifier qu'un test d'annuaire réussit : c'est lui qui prouve que la clé correspond aux mots de passe.

## Base de données

core-service ne peut pas lire la connexion à sa base dans cette même base : elle est écrite dans
`config/runtime/database.json` (monté en lecture-écriture dans core-service, `B2S_RUNTIME_DIR`) et remplace les `DB_*` du `.env`
**au prochain démarrage de core-service**.

- Saisie par champs (serveur, port, base, base d'audit, compte, mot de passe) ou par chaîne de connexion (DSN), qui remplace les champs.
- Le test se connecte, donne la version et vérifie la présence du schéma BornToShare. L'enregistrement n'est possible
  qu'après un test réussi des mêmes valeurs ; le serveur teste à nouveau avant d'écrire.
- Le fichier contient le mot de passe, comme le `.env` : il est écrit en 0600 et ignoré par git. L'interface ne le relit jamais.
- « Revenir aux réglages du .env » supprime le fichier (appliqué au prochain démarrage).
- Seul core-service lit ce fichier. L'assistant d'installation (wizard-ui) garde ses propres réglages.

## Workers

Un worker (capsule-runner) lit ses tâches dans la file Redis ; il expose en plus un **agent HTTPS** que core-service interroge
(processus actifs, file joignable, tâches en attente, version, vérification LDAPS).

Sur le worker (`.env`) :

```
INTERNAL_TOKEN=<le même que core-service>
AGENT_TLS_CERT=/etc/b2s/certs/agent.pem     # HTTPS (recommandé)
AGENT_TLS_KEY=/etc/b2s/certs/agent.key
```

Port : 8443 en HTTPS ; **sans certificat, l'agent répond en HTTP sur le port 8080** (décocher « HTTPS » dans le formulaire).
`AGENT_PORT` change le port dans les deux cas. À ouvrir de core-service vers le worker uniquement ; le HTTP est réservé
à un réseau interne (l'échange avec l'agent n'y est pas chiffré). Certificat d'une autorité privée :
la donner à core-service avec `B2S_AGENT_CA_FILE`, ou décocher « Vérifier le certificat » dans le formulaire.

Dans l'interface : nom, adresse IP ou nom DNS, port de l'agent. Le worker n'est ajouté que si son agent
répond. core-service se présente à l'agent avec une preuve dérivée de `INTERNAL_TOKEN`, sans compte à stocker.

| Message | Cause |
|---|---|
| « L'agent a refusé ce serveur » | `INTERNAL_TOKEN` différent sur le worker |
| « Certificat de l'agent refusé » | autorité inconnue : `B2S_AGENT_CA_FILE` ou décocher la vérification |
| « L'agent a fermé la connexion » | HTTPS d'un côté, HTTP de l'autre : aligner la case TLS et `AGENT_TLS_CERT` |
| « Pas de réponse » | hôte, port ou pare-feu |
| dégradé : « aucun processus de tâches » / « file injoignable » | le worker répond mais ne peut pas exécuter de tâches |

## Composants surveillés

Les services de la plateforme sont pré-remplis (adresse modifiable, désactivables, non supprimables).
Ajoutez tout autre composant à contrôler depuis un worker : URL `http(s)://…` (réponse < 500) ou `hôte:port` (port ouvert).

## Journal d'audit

Tracés : connexion de base enregistrée ou réinitialisée, worker ajouté, modifié, supprimé, planification modifiée,
tâche lancée à la main, composant ajouté, modifié, supprimé.

## Premier démarrage

Tant qu'aucun dossier n'est gouverné et que le parcours n'est pas terminé, un administrateur qui se connecte arrive sur `/setup` :
zone, annuaire (Active Directory ou OpenLDAP, en LDAP ou LDAPS), serveur de fichiers, identités, rôles, premiers dossiers et leurs garants.
À la fin, le worker de l'installation est déclaré tout seul dans Infrastructure. Chaque étape est enregistrée et
le parcours reprend à la première étape restante. Le compte administrateur local est créé avant, par `wizard-ui`.

## Annuaires OpenLDAP

Les utilisateurs sont lus dans `inetOrgPerson` ou `posixAccount` (identifiant `uid`), les groupes dans `groupOfNames` ou
`groupOfUniqueNames`, l'identifiant stable est `entryUUID`. BornToShare crée des `groupOfNames` ; comme ce type de groupe ne peut pas être
vide, le groupe est inscrit comme son propre membre, et cette entrée est ignorée à la lecture. OpenLDAP n'indique pas de compte désactivé
de façon standard : un compte est considéré actif tant qu'il peut se connecter.

Limite : les droits sur les dossiers portent sur le nom du groupe. Le serveur de fichiers doit donc connaître ces groupes, par exemple
un Samba adossé au même annuaire. Un serveur Windows membre d'un domaine AD ne voit pas les groupes d'un OpenLDAP.

