Certificat (PEM) de l'autorité de certification Active Directory, monté en lecture seule
dans capsule-runner sur /etc/b2s/certs.

Production : déposer `ad-ca.pem` ici, puis dans `.env` :

    LDAP_TLS_VERIFY=true
    LDAP_CA_FILE=/etc/b2s/certs/ad-ca.pem

Les fichiers de ce dossier (hors ce README) ne sont pas versionnés.
