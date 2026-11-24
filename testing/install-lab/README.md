# Labo d'installation (tests du wizard)

Joue une vraie installation de BornToShare (`make wizard`, l'API du wizard, puis `scripts/after-wizard.sh` et
`scripts/deploy.sh`) sur des **hôtes simulés** : un conteneur par machine, avec son nom d'hôte, son adresse, son
propre Podman et ses volumes, sur un réseau isolé **sans accès Internet**. Rien de ce dossier ne fait partie d'une
installation.

```bash
testing/install-lab/lab.sh run containers   # lab-db + lab-app (tout en conteneurs)
testing/install-lab/lab.sh run hybrid       # lab-db + lab-app + lab-web (interface sur un serveur annexe, par SSH)
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
| `lab-web` | serveur web annexe (hybride) : systemd, httpd + mod_ssl, Node.js 22, sshd, compte `labdeploy` (sudo) | `Containerfile.web-host` |
| contrôleur | joue le wizard par son API et le premier parcours dans un navigateur (Playwright) | `localhost/b2s-pw` |

Les images produit sont celles du dépôt (`localhost/b2s-*:latest`) : archivées une fois (`lab.sh images`), puis
chargées dans chaque hôte ; rien n'est construit dans le labo (`podman-compose-lab` ignore `build`). Le code
déployé est l'état commité (`git archive HEAD`), donné dans le rapport.

Contrôles : prérequis, base vérifiée, installation, phases du déploiement, `.env` complété, secrets podman,
images en service, healthchecks, connectivité (core → base, Redis, auth, worker ; annexe → API), bases
initialisées, page de connexion et première connexion, en hybride le vhost, le certificat et les unités systemd de
l'annexe ; puis une deuxième installation (`make deploy`), un redémarrage, une panne de la base et son retour.

Limites : le mode **natif** n'est pas couvert (systemd des services, comptes système, Python du système : à
valider sur une vraie VM) ; SELinux et firewalld ne sont pas actifs dans les hôtes simulés.
