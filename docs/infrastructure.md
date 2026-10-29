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
(certificat vérifié si `LDAP_TLS_VERIFY=true`), bind avec le compte qui lit l'annuaire (compte « snapshot »,
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
AGENT_USERNAME=b2s-agent
AGENT_PASSWORD=<mot de passe long>
AGENT_TLS_CERT=/etc/b2s/certs/agent.pem     # HTTPS (recommandé)
AGENT_TLS_KEY=/etc/b2s/certs/agent.key
```

Port : 8443 en HTTPS ; **sans certificat, l'agent répond en HTTP sur le port 8080** (décocher « HTTPS » dans le formulaire).
`AGENT_PORT` change le port dans les deux cas. À ouvrir de core-service vers le worker uniquement ; le HTTP est réservé
à un réseau interne (le mot de passe de l'agent y circule en clair). Certificat d'une autorité privée :
la donner à core-service avec `B2S_AGENT_CA_FILE`, ou décocher « Vérifier le certificat » dans le formulaire.

Dans l'interface : nom, adresse IP ou nom DNS, port, utilisateur et mot de passe de l'agent. Le worker n'est ajouté que si son agent
répond avec ces identifiants. Le mot de passe est rangé dans le secret broker ; core-service le lit uniquement pour interroger l'agent.

| Message | Cause |
|---|---|
| « L'agent a refusé le nom d'utilisateur ou le mot de passe » | identifiants différents de `AGENT_USERNAME` / `AGENT_PASSWORD` |
| « L'agent n'a pas d'identifiants configurés » | `AGENT_USERNAME` / `AGENT_PASSWORD` absents sur le worker |
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
