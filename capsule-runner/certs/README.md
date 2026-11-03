Certificats montés en lecture seule sur /etc/b2s/certs (auth-service, core-service, capsule-runner). Chaque
fichier est pris en compte s'il existe, sans variable :

- `agent.crt` + `agent.key` : agent du worker en HTTPS sur 8443 (sinon HTTP sur 8080, réseau interne uniquement) ;
- `agent-ca.pem` : autorité privée des certificats d'agent, lue par core-service ;
- `oidc-ca.pem` : autorité privée des serveurs Keycloak, lue par auth-service (SSO).

L'autorité de certification Active Directory ne se dépose pas ici : elle se colle dans le formulaire de l'annuaire et reste en base.

Les fichiers de ce dossier (hors ce README) ne sont pas versionnés.
