#!/bin/bash
# First start: provisions the domain, its LDAPS certificate and the test data (seed.sh); then runs Samba.
set -euo pipefail

REALM="${AD_LAB_REALM:-EXAMPLE.TEST}"
DOMAIN="${AD_LAB_DOMAIN:-EXAMPLE}"
HOST_FQDN="$(hostname -s).${REALM,,}"
ADMIN_PASSWORD="${AD_LAB_ADMIN_PASSWORD:?AD_LAB_ADMIN_PASSWORD must be set}"
TLS_DIR=/var/lib/samba/private/tls
EXPORT_DIR=/export
# smb.conf is kept in the volume: a recreated container (new image) finds the domain and its shares
SAVED_CONF=/var/lib/samba/smb.conf

if [ ! -f /var/lib/samba/private/sam.ldb ]; then
  echo "ad-lab: provisioning ${REALM} (${HOST_FQDN})"
  rm -f /etc/samba/smb.conf
  samba-tool domain provision \
    --realm="${REALM}" --domain="${DOMAIN}" --server-role=dc --dns-backend=SAMBA_INTERNAL \
    --adminpass="${ADMIN_PASSWORD}" \
    --option="acl_xattr:security_acl_name = user.NTACL" \
    --option="dns forwarder = 127.0.0.11" \
    --option="dns update command = /bin/true" >/dev/null

  # LDAPS: our own CA, so that BornToShare can verify the certificate (LDAP_TLS_VERIFY=true)
  mkdir -p "${TLS_DIR}"
  # Extensions required by strict X.509 checks (Python 3.13+ ssl, recent OpenSSL clients)
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=BornToShare AD lab CA" \
    -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash" \
    -keyout "${TLS_DIR}/ca.key" -out "${TLS_DIR}/ca.pem" 2>/dev/null
  openssl req -newkey rsa:2048 -nodes -subj "/CN=${HOST_FQDN}" \
    -keyout "${TLS_DIR}/key.pem" -out "${TLS_DIR}/dc.csr" 2>/dev/null
  printf "%s\n" "basicConstraints=CA:FALSE" "keyUsage=critical,digitalSignature,keyEncipherment" \
    "extendedKeyUsage=serverAuth" "subjectAltName=DNS:${HOST_FQDN},DNS:$(hostname -s)" \
    "subjectKeyIdentifier=hash" "authorityKeyIdentifier=keyid,issuer" > "${TLS_DIR}/dc.ext"
  openssl x509 -req -in "${TLS_DIR}/dc.csr" -CA "${TLS_DIR}/ca.pem" -CAkey "${TLS_DIR}/ca.key" -CAcreateserial \
    -days 3650 -extfile "${TLS_DIR}/dc.ext" -out "${TLS_DIR}/cert.pem" 2>/dev/null
  chmod 600 "${TLS_DIR}/key.pem" "${TLS_DIR}/ca.key"

  sed -i "/^\[global\]/a \\
\ttls enabled = yes\\
\ttls keyfile = ${TLS_DIR}/key.pem\\
\ttls certfile = ${TLS_DIR}/cert.pem\\
\ttls cafile = ${TLS_DIR}/ca.pem\\
\tldap server require strong auth = no" /etc/samba/smb.conf

  /usr/local/bin/seed.sh
  cp /etc/samba/smb.conf "${SAVED_CONF}"
else
  cp "${SAVED_CONF}" /etc/samba/smb.conf
fi

# The CA is published for the containers that check LDAPS (capsule-runner, auth-service)
if [ -d "${EXPORT_DIR}" ]; then
  cp "${TLS_DIR}/ca.pem" "${EXPORT_DIR}/ad-ca.pem"
  chmod 644 "${EXPORT_DIR}/ad-ca.pem"
fi

# First start: NTFS permissions of the shares once smbd answers (only administrators and svc-b2s-files,
# so that every access really comes from a BornToShare group)
if [ -f /var/lib/samba/.acl-pending ]; then
  (
    auth="$(mktemp)"; chmod 600 "${auth}"
    printf "username = Administrator\npassword = %s\ndomain = %s\n" "${ADMIN_PASSWORD}" "${DOMAIN}" > "${auth}"
    for _ in $(seq 1 60); do smbclient -L localhost -A "${auth}" >/dev/null 2>&1 && break; sleep 2; done
    acl="ACL:NT AUTHORITY\\SYSTEM:ALLOWED/OI|CI/FULL,ACL:BUILTIN\\Administrators:ALLOWED/OI|CI/FULL"
    acl="${acl},ACL:${DOMAIN}\\Domain Admins:ALLOWED/OI|CI/FULL,ACL:${DOMAIN}\\svc-b2s-files:ALLOWED/OI|CI/FULL"
    for target in "corp:" "corp:finance" "corp:hr" "corp:legal" "projects:" "projects:alpha" "projects:beta"; do
      share="${target%%:*}"; folder="${target#*:}"
      smbcacls "//localhost/${share}" "${folder:-\\}" -A "${auth}" --set "${acl}" >/dev/null
    done
    rm -f "${auth}" /var/lib/samba/.acl-pending
    echo "ad-lab: share permissions set"
  ) &
fi

exec samba -i --debug-stdout -d 1
