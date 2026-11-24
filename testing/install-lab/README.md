# Labo d'installation (tests du wizard)

Joue une vraie installation de BornToShare (`make wizard`, l'API du wizard, puis `scripts/after-wizard.sh` et
`scripts/deploy.sh`) sur des **hôtes simulés** : un conteneur par machine, avec son nom d'hôte, son adresse, son
propre Podman et ses volumes, sur un réseau isolé **sans accès Internet**. Rien de ce dossier ne fait partie d'une
installation.

```bash
testing/install-lab/lab.sh run containers   # lab-db + lab-app (tout en conteneurs)
testing/install-lab/lab.sh run hybrid       # lab-db + lab-app + lab-web (interface sur un serveur annexe, par SSH)
testing/install-lab/lab.sh run faults       # installation hybride puis pannes une à une (message attendu, puis reprise)
testing/install-lab/lab.sh run native       # lab-db + lab-app en natif (systemd), essai partiel, accès Internet (pip, npm)
B2S_LAB_DRIVE=api testing/install-lab/lab.sh run containers   # le wizard par son API au lieu de ses écrans
testing/install-lab/lab.sh report           # synthèse par mode
testing/install-lab/lab.sh down hybrid      # nettoyage après une interruption
```

Un scénario crée son environnement, installe, vérifie, puis détruit tout (conteneurs, réseau, stockage, mots de
passe et clé SSH de l'exécution) et vérifie qu'il ne reste rien. Le rapport, la configuration générée (secrets
masqués) et le journal du déploiement restent dans `~/.cache/b2s-install-lab/runs/<date>-<scénario>/`
(`B2S_LAB_CACHE` pour un autre dossier).

| Hôte | Rôle | Image |
|---|---|---|
| `lab-db` | MariaDB 11.4, mot de passe root propre à l'exécution | `mariadb:11.4` |
| `lab-app` | serveur BornToShare : Podman imbriqué, `podman-compose`, `make` | `Containerfile.app-host` |
| `lab-app` (natif) | systemd, Python 3.12, Redis du système, Node.js 26 + npm, httpd, gcc et krb5 pour le worker | `Containerfile.native-host` |
| `lab-web` | serveur web annexe (hybride) : systemd, httpd + mod_ssl, Node.js 26, sshd, compte `labdeploy` (sudo) | `Containerfile.web-host` |
| contrôleur | joue le wizard par ses écrans (ou son API) et le premier parcours dans un navigateur (Playwright) | `localhost/b2s-pw` |

Les images produit sont celles du dépôt (`localhost/b2s-*:latest`) : archivées une fois (`lab.sh images`), puis
chargées dans chaque hôte ; rien n'est construit dans le labo (`podman-compose-lab` ignore `build`). Le code
déployé est l'état commité (`git archive HEAD`), donné dans le rapport.

Contrôles : prérequis, base vérifiée, installation, phases du déploiement, `.env` complété, secrets podman,
images en service, healthchecks, connectivité (core → base, Redis, auth, worker ; annexe → API), bases
initialisées, page de connexion et première connexion, en hybride le vhost, le certificat et les unités systemd de
l'annexe ; puis une deuxième installation (`make deploy`), un redémarrage, une panne de la base et son retour.

Pannes (`faults`) : DNS faux et port fermé au Wizard, base arrêtée pendant un déploiement, Redis et worker
arrêtés, image absente sans registre, annexe injoignable, clé SSH inconnue, compte sans sudo, clé d'hôte changée,
certificat introuvable, `.env` incomplet ; chacune doit échouer avec sa cause, puis `make deploy` reprend.

Limites : le natif est un essai partiel (un conteneur avec systemd n'est pas un serveur) ; SELinux et firewalld ne
sont actifs dans aucun hôte simulé : à valider sur une vraie VM.
