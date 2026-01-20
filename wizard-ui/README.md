# 🧙 BornToShare – Wizard UI

Le **Wizard UI** est l’outil officiel d’initialisation de la plateforme **BornToShare**.

Il permet de **préparer, valider et générer** l’ensemble des éléments nécessaires au premier démarrage de la plateforme, sans manipulation manuelle de fichiers sensibles.

---

## 🎯 Objectif

- Initialisation de la base de données
- Déploiement du schéma SQL et des vues
- Création des comptes applicatifs
- Génération des fichiers `.env.*`
- Validation des prérequis techniques

Le Wizard est conçu pour être utilisé **une seule fois**, lors du bootstrap initial.

---

## 🧩 Étapes couvertes

1. Présentation
2. Administrateur applicatif
3. Connexion DB (root)
4. Base & comptes applicatifs
5. Comptes services
6. Vérifications
7. Résumé global
8. Import final

Chaque étape est bloquante si invalide.

---

## 🛡️ Sécurité

- Aucun secret versionné
- Aucune valeur par défaut sensible
- Validation stricte des mots de passe
- Génération locale des fichiers `.env`

---

## ⚙️ Prérequis

- MariaDB / MySQL accessible
- Droits root DB
- Docker ou Podman
- Services BornToShare arrêtés

---

## 🚀 Lancement

```bash
docker run -p 8080:8080 borntoshare/wizard-ui
```

Accès via http://localhost:8080

---

## 📄 Fichiers générés

- `.env.dal`
- `.env.auth`
- `.env.governance`

Ces fichiers ne doivent jamais être commités.

---

## 📘 Variables d’environnement

Les variables possibles sont documentées dans le README principal du projet BornToShare sous forme de tableaux explicites.

---

## 🖼️ Captures d’écran

Les images du Wizard peuvent être ajoutées dans le dossier `images/`.

---

## 🏁 Conclusion

Le Wizard UI garantit une initialisation sécurisée, cohérente et reproductible de la plateforme BornToShare.

© BornToShare
