#!/bin/bash
# Test data of the lab domain (first start only). Same layout as a small Windows AD:
#   OU=Staff         people who request accesses
#   OU=Service Accounts
#   OU=B2S Groups    where BornToShare creates the access groups (delegated to svc-b2s-prov only)
#   shares corp (finance, hr, legal) and projects (alpha, beta), NTFS ACLs without « Everyone »
set -euo pipefail

REALM="${AD_LAB_REALM:-EXAMPLE.TEST}"
BASE_DN="DC=${REALM,,}"; BASE_DN="${BASE_DN//./,DC=}"
USER_PASSWORD="${AD_LAB_USER_PASSWORD:?AD_LAB_USER_PASSWORD must be set}"
SERVICE_PASSWORD="${AD_LAB_SERVICE_PASSWORD:?AD_LAB_SERVICE_PASSWORD must be set}"

# Lab passwords never expire (tests run for months)
samba-tool domain passwordsettings set --max-pwd-age=0 --min-pwd-age=0 >/dev/null

for ou in "Staff" "Service Accounts" "B2S Groups"; do
  samba-tool ou create "OU=${ou},${BASE_DN}" >/dev/null
done

user() {  # login given surname department
  samba-tool user create "$1" "${USER_PASSWORD}" --given-name="$2" --surname="$3" \
    --department="$4" --mail-address="$1@${REALM,,}" --userou="OU=Staff" >/dev/null
}
user paul.martin Paul Martin Projects
user jane.doe Jane Doe Finance
user lucie.user Lucie User HR
user claire.auditor Claire Auditor Audit
user alice.finance Alice Finance Finance
user marc.admin Marc Admin IT

# Department groups (imported by BornToShare, used to sign in)
samba-tool group add GG_Finance --groupou="OU=Staff" --description="Finance department" >/dev/null
samba-tool group add GG_HR --groupou="OU=Staff" --description="Human resources" >/dev/null
samba-tool group add GG_Projects --groupou="OU=Staff" --description="Project teams" >/dev/null
samba-tool group add GG_B2S_Admins --groupou="OU=Staff" --description="BornToShare platform administrators" >/dev/null
samba-tool group addmembers GG_Finance jane.doe,alice.finance >/dev/null
samba-tool group addmembers GG_HR lucie.user >/dev/null
samba-tool group addmembers GG_Projects paul.martin >/dev/null
samba-tool group addmembers GG_B2S_Admins marc.admin >/dev/null

# One service account per capability (Identity sources › service accounts)
service() {  # login description
  samba-tool user create "$1" "${SERVICE_PASSWORD}" --userou="OU=Service Accounts" --description="$2" >/dev/null
  samba-tool user setexpiry "$1" --noexpiry >/dev/null
}
service svc-b2s-read "BornToShare: directory snapshot and sign-in (read only)"
service svc-b2s-prov "BornToShare: creates the access groups and their members in OU=B2S Groups"
service svc-b2s-files "BornToShare: NTFS permissions of the shares"

# svc-b2s-prov manages OU=B2S Groups only (create/delete children, write properties), like a Windows delegation
PROV_SID="$(samba-tool user show svc-b2s-prov --attributes=objectSid | awk '/^objectSid:/ {print $2}')"
samba-tool dsacl set --objectdn="OU=B2S Groups,${BASE_DN}" --action=allow \
  --sddl="(A;CI;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;${PROV_SID})" >/dev/null

# Shares: the folders exist now, their ACL is set once smbd answers (entry.sh, .acl-pending)
mkdir -p /srv/shares/corp/{finance,hr,legal} /srv/shares/projects/{alpha,beta}
cat >> /etc/samba/smb.conf <<CONF

[corp]
   path = /srv/shares/corp
   read only = no
   vfs objects = acl_xattr
   acl_xattr:ignore system acls = yes

[projects]
   path = /srv/shares/projects
   read only = no
   vfs objects = acl_xattr
   acl_xattr:ignore system acls = yes
CONF
touch /var/lib/samba/.acl-pending
echo "ad-lab: seeded (6 users, 4 groups, 3 service accounts, shares corp and projects)"
