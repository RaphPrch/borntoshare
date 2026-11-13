# Notifications par e-mail

Réglages avancés › **Notifications** (administrateurs). Les e-mails partent en arrière-plan, depuis core-service,
par le serveur SMTP réglé ici. Un même message n'est jamais envoyé deux fois (clé unique, table `notification_log`,
avec l'état « envoyé » ou « échec » et la raison).

## Les messages

| Message | Destinataires | Quand |
|---|---|---|
| Nouvelle demande d'accès | les gardiens du dossier (et leurs suppléants en vigueur) | à la création de la demande |
| Accès accordé, ou demande refusée | le demandeur | à la décision |
| Rappel de fin d'accès | le titulaire de l'accès | N jours avant la fin (réglable, 0 = aucun), une seule fois |
| Fichiers sensibles ouverts à tous | les gardiens du dossier | à l'ouverture de l'alerte, pas à chaque scan (voir [sensibilite.md](sensibilite.md)) |
| Politique | les gardiens du dossier | quand une politique qui notifie s'applique à un dossier |
| Panne d'infrastructure | les administrateurs de la plateforme | un serveur devient injoignable (alerte ouverte), ou le contrôle de santé trouve en panne un composant qui fonctionnait ; une fois par panne (case « Une panne… : aux administrateurs ») |
| E-mail de test | l'adresse saisie | bouton « Tester » |

Chaque e-mail part en HTML **et** en texte : un client qui n'affiche pas le HTML montre le texte. Le HTML suit les
règles des clients de messagerie (tableaux, styles dans les balises, ni image ni script, polices du système en
secours) ; la mise en page est dans `core-service/app/services/mail_templates.py`, et chaque valeur y est échappée.
Les liens mènent à l'application (« Adresse de BornToShare dans les e-mails ») ; aucune décision ne se prend depuis
un e-mail.

## Dans l'application : la cloche

Les mêmes événements arrivent aussi dans la cloche du menu (centre de notifications), **que l'e-mail soit activé ou
non** et même sans adresse sur le compte : nouvelle demande pour les gardiens du dossier (les administrateurs s'il n'a
aucun gardien), décision pour le demandeur, fin d'accès proche pour son titulaire, panne pour les administrateurs.
Une notification par personne et par événement (table `user_notifications`, pack SQL 161) ; « Tout marquer comme lu »
ne concerne que soi.

L'application est tenue à jour sans recharger : le navigateur garde une connexion ouverte sur `/live`
(Server-Sent Events), par laquelle le serveur pousse, toutes les 5 secondes et seulement quand ils changent, les
notifications non lues, le nombre de demandes en attente, les alertes critiques et, pour les administrateurs, les
tâches en cours (volet en bas à gauche). Une page dont les données ont bougé (demandes, alertes) se recharge seule.
Derrière un proxy inverse, ne pas mettre en tampon les réponses `text/event-stream` (l'en-tête
`X-Accel-Buffering: no` est envoyé pour nginx).

## Régler le serveur SMTP

| Champ | Effet |
|---|---|
| Serveur, port, sécurité | `STARTTLS` (587), `TLS` (465) ou aucune (réseau interne seulement) |
| Expéditeur | adresse `From` ; avec un service hébergé, la même que le compte |
| Compte, mot de passe | facultatifs ; le mot de passe est chiffré dans le coffre et jamais relu par l'interface |
| Adresse de BornToShare | base des liens dans les e-mails |
| E-mails envoyés | cases par message ; jours de rappel avant la fin d'un accès |

### Gmail

Port 587, STARTTLS, l'adresse Gmail comme compte **et** comme expéditeur, et un **mot de passe d'application**
(16 lettres : Compte Google › Sécurité › Mots de passe des applications, validation en deux étapes activée). Le
mot de passe habituel du compte est refusé par Gmail. Erreurs courantes :

| Message | Cause |
|---|---|
| `SMTP AUTH extension not supported by server` | sécurité réglée sur « aucune » : Gmail n'authentifie qu'après STARTTLS |
| `Connection unexpectedly closed` à l'authentification | mot de passe refusé : utiliser un mot de passe d'application |

### Serveur de test (laboratoire)

`make mail-up` démarre **Mailpit** (profil `mail` de `podman-compose.yml`) : il reçoit tous les e-mails de
BornToShare, n'en envoie aucun au dehors, et les affiche sur `http://<hôte>:8025`. Réglage : serveur `mailpit`,
port `1025`, sécurité aucune, sans compte. Les messages sont gardés en mémoire (2 000 au plus) ; `make mail-down`
l'arrête. Jamais en production.

## Destinataires

Les adresses sont celles des identités. Pour un compte de l'annuaire, elle est reprise de l'attribut `mail` de l'AD
quand l'identité est importée (Identités › Créer › Utilisateur de l'annuaire, ou un nouvel import du même compte).
Un gardien sans adresse ne reçoit rien : la liste des destinataires est vide et rien n'est envoyé.
