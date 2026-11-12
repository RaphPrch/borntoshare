# Pilote sur Active Directory et serveur de fichiers Windows

Objectif : vérifier sur de vrais serveurs Windows ce qui n'a été testé que sur le labo Samba
(`testing/ad-lab`), avant la mise en production. Durée à prévoir : une demi-journée.

Chaque étape indique le résultat attendu. Noter tout écart, avec l'heure et le message affiché.

## Préparation côté Windows

Tous les noms ci-dessous sont des exemples, à adapter.

**Comptes de service**, ni administrateurs du domaine ni membres d'un groupe, marqués « sensible, ne peut pas être
délégué » ; droits exacts et vérification : [droits-ad.md](droits-ad.md).

| Compte | Sert à | Droits |
|---|---|---|
| `svc-b2s-sync` | inventaire, recherche, santé de l'annuaire | lecture par défaut, rien à ajouter |
| `svc-b2s-auth` | connexion des utilisateurs | lecture par défaut, rien à ajouter |
| `svc-b2s-prov` | création des groupes et des membres | délégation sur l'OU ci-dessous |
| `svc-b2s-files` | ACL, dossiers, mesures, sensibilité, quotas | administrateur local du serveur de fichiers, aucun droit dans l'AD |

**OU dédiée** aux groupes, par exemple `OU=B2S Groups,DC=example,DC=test`, avec la délégation :

```bat
dsacls "OU=B2S Groups,DC=example,DC=test" /G "EXAMPLE\svc-b2s-prov:CC;group"
dsacls "OU=B2S Groups,DC=example,DC=test" /I:S /G "EXAMPLE\svc-b2s-prov:WP;member;group"
```

Le groupe qui donnera le rôle d'administrateur de BornToShare (`GG_B2S_Pilot_Admins` ci-dessous) se range **hors**
de cette OU, ou reçoit un refus explicite (`dsacls "<DN du groupe>" /D "EXAMPLE\svc-b2s-prov:WP;member"`).

**Serveur de fichiers** : un partage de test, par exemple `\\files.example.test\pilote`, contenant trois dossiers.
`svc-b2s-files` est administrateur local du serveur : lecture et pose des ACL, création de partages, quotas FSRM, et
PowerShell à distance (WinRM 5985, Kerberos) pour les mesures et la sensibilité. Le serveur se déclare de préférence
par son nom DNS (Kerberos).

**Utilisateurs et groupes de test** :

- `pilote.admin`, membre d'un groupe `GG_B2S_Pilot_Admins` ;
- `pilote.garant` et `pilote.user`, sans groupe particulier ;
- un compte désactivé et un compte dont le mot de passe a expiré.

**Réseau**, depuis le worker : LDAPS 636 et Kerberos 88 vers le contrôleur de domaine, SMB 445 et WinRM 5985 vers le serveur de fichiers.

**Certificat** : l'autorité qui signe le certificat LDAPS, au format PEM. Elle se colle dans le formulaire de l'annuaire.

Les mots de passe sont saisis dans l'interface, qui les chiffre en base. Ne pas les transmettre autrement.

## 1. Connexion

| # | Action | Résultat attendu |
|---|---|---|
| 1.1 | Annuaires › Nouvel annuaire, avec les comptes ci-dessus, puis Tester la connexion | Test réussi, certificat vérifié |
| 1.1b | Observabilité › Santé, après un contrôle | Ligne « Group OU » de l'OU dédiée : opérationnelle (le compte de provisioning peut y créer des groupes) |
| 1.2 | Synchroniser maintenant | Utilisateurs, groupes et appartenances au bon nombre, comparés à l'AD |
| 1.3 | Identités › Créer › Groupe de l'annuaire : `GG_B2S_Pilot_Admins`, rôle administrateur | Le groupe apparaît, « Voir les membres » liste `pilote.admin` |
| 1.4 | Connexion avec `pilote.admin`, puis `EXAMPLE\pilote.admin`, puis `pilote.admin@example.test` | Accès administrateur les trois fois |
| 1.5 | Connexion du compte désactivé, puis du compte expiré | Refus avec un message clair |
| 1.6 | 5 mauvais mots de passe avec `pilote.user`, puis le bon | Blocage temporaire de 15 min ; le compte n'est **pas** verrouillé dans l'AD si le seuil du domaine est supérieur à 5 |

## 2. Serveur de fichiers et dossiers

| # | Action | Résultat attendu |
|---|---|---|
| 2.1 | Serveurs › Ajouter un serveur, découverte des partages | Le partage et ses dossiers sont listés |
| 2.2 | Dossiers › Ajouter des dossiers : les trois dossiers | Tuiles visibles, zone et serveur corrects |
| 2.3 | Ouvrir un dossier › Relire l'ACL | Les entrées existantes sont lues ; les noms correspondent à ceux de l'Explorateur Windows |
| 2.4 | Nommer `pilote.garant` gardien du premier dossier ; laisser le deuxième sans gardien | `pilote.garant` voit ce dossier et seulement lui ; le dossier sans gardien est signalé « Sans gardien » et ses demandes vont aux administrateurs |
| 2.5 | `pilote.garant` essaie de se retirer des garants | Refus, tentative tracée dans le journal |

## 3. Demande et approbation

| # | Action | Résultat attendu |
|---|---|---|
| 3.1 | `pilote.user` demande la lecture sur le premier dossier | Demande en attente, visible par le garant |
| 3.2 | Le garant ouvre la demande, puis approuve | Groupe créé dans l'OU dédiée, membre ajouté, demande « Approuvée » |
| 3.3 | Dans l'AD : Utilisateurs et ordinateurs | Groupe global de sécurité, bon nom, bonne OU, `pilote.user` membre |
| 3.4 | Sur le dossier : Propriétés › Sécurité | Le groupe a Lecture et exécution, héritée par les sous-dossiers |
| 3.5 | `pilote.user` ouvre une **nouvelle** session Windows et accède au dossier | Lecture possible, écriture refusée |
| 3.6 | Demande de modification, approuvée, nouvelle session | Écriture possible |
| 3.7 | Révocation | Membre retiré, groupe et ACL conservés ; accès perdu à la session suivante |
| 3.8 | Accès avec date de fin proche, attendre l'échéance | Membre retiré automatiquement |
| 3.9 | Cocher plusieurs demandes › Tout approuver | Progression affichée, toutes appliquées |
| 3.10 | `pilote.garant` dépose une demande pour lui-même | Il ne peut pas l'approuver ni la prolonger ; un autre garant ou un administrateur décide, tentative tracée |
| 3.11 | Avant la décision, Passer en lecture ou en écriture avec une raison | Niveau changé, demande d'origine et raison visibles, changement tracé |

Le ticket Kerberos d'une session ouverte ne contient pas le nouveau groupe : c'est pourquoi les étapes 3.5 à 3.7 demandent une nouvelle session.

## 4. Écarts et héritage

| # | Action | Résultat attendu |
|---|---|---|
| 4.1 | Ajouter à la main une entrée sur un dossier gouverné, puis Relire l'ACL | Écart signalé dans Permissions |
| 4.2 | Ajouter à la main un membre à un groupe BornToShare, puis synchroniser | Alerte « membre du groupe AD sans accès accordé » |
| 4.3 | Retirer le groupe de l'ACL, puis Relire l'ACL | Alerte bloquante ; réapprouver répare l'ACL |
| 4.4 | Rompre puis rétablir l'héritage depuis l'interface | État identique à celui de l'onglet Sécurité de Windows |
| 4.5 | Créer un sous-dossier, puis le supprimer depuis l'interface | Effectif sur le serveur ; suppression refusée tant que des accès sont actifs |
| 4.6 | Dossier avec des noms accentués et des espaces | Noms, ACL et accès corrects |

## 5. Pannes

| # | Action | Résultat attendu |
|---|---|---|
| 5.1 | Couper le 445 vers le serveur de fichiers, approuver | Demande en attente, message clair ; serveur « en panne » dans Suivi |
| 5.2 | Rétablir, réapprouver | Appliquée, rien en double |
| 5.3 | Changer le mot de passe de `svc-b2s-read` | Annuaire « en panne » avec la cause, au plus tard une heure après (délai propre à AD) |
| 5.4 | Avec deux contrôleurs dans l'hôte de l'annuaire (`dc01, dc02`), arrêter le premier | Connexions, synchronisation et approbations passent par le second ; Observabilité › Santé montre le premier en panne et les administrateurs reçoivent un e-mail |

## 6. Volume réel

Mesurer sur le parc du pilote, ou sur un échantillon représentatif :

- durée de l'inventaire et de la synchronisation complète (Réglages › Infrastructure › Planification) ;
- durée d'une lecture d'ACL sur un dossier contenant beaucoup de sous-dossiers ;
- temps d'affichage de Dossiers et de Demandes.

## Bilan

Le pilote est réussi si les étapes 1 à 5 donnent le résultat attendu, ou si chaque écart est corrigé ou accepté par écrit.
