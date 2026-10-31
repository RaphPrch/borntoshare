"""What differs between the kinds of LDAP directory: object classes and attribute names (from the job's directory_flavor)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def escape_filter(value: str) -> str:
    return (
        str(value or "")
        .replace("\\", "\\5c")
        .replace("*", "\\2a")
        .replace("(", "\\28")
        .replace(")", "\\29")
        .replace("\x00", "")
    )


@dataclass(frozen=True)
class Dialect:
    name: str
    user_filter: str
    group_filter: str
    group_classes: tuple[str, ...]
    user_classes: frozenset[str]
    id_attr: str
    login_attr: str
    upn_attr: str
    group_login_attr: str
    changed_attr: str
    ou_filter: str = "(objectClass=organizationalUnit)"
    sid_attr: str | None = None
    usn_attr: str | None = None

    def is_group(self, classes: set[str]) -> bool:
        return bool(classes & {c.lower() for c in self.group_classes} or classes & {"group", "groupofnames", "groupofuniquenames"})

    def is_user(self, classes: set[str]) -> bool:
        return bool(classes & self.user_classes) and "computer" not in classes

    def attrs(self, *names: str | None) -> list[str]:
        return [name for name in names if name]

    def group_ref_filter(self, value: str) -> str:
        escaped = escape_filter(value)
        by_name = f"(cn={escaped})" if self.group_login_attr == "cn" else f"(cn={escaped})({self.group_login_attr}={escaped})"
        return f"(&{self.group_filter}(|{by_name}))"

    def user_ref_filter(self, value: str) -> str:
        escaped = escape_filter(value)
        classes = "".join(f"(objectClass={name})" for name in sorted(self.user_classes))
        return f"(&(|{classes})(|({self.login_attr}={escaped})({self.upn_attr}={escaped})(cn={escaped})))"

    def id_filter(self, value: str) -> str | None:
        """Group or user by its stable identifier; None when the directory has its own binary form (handled by the caller)."""
        return f"({self.id_attr}={escape_filter(value)})" if self.name == "openldap" else None

    def new_group(self, *, group_dn: str, group_name: str, description: str, marker: str) -> tuple[list[str], dict[str, Any]]:
        """Object classes and attributes of a group to create."""
        if self.name == "openldap":
            # groupOfNames needs one member at least: the group itself holds the place, so it can stay empty of people
            return ["top", "groupOfNames"], {"cn": group_name, "member": [group_dn], "description": description or marker}
        return ["top", "group"], {
            "sAMAccountName": group_name,
            "groupType": -2147483646,  # GLOBAL + SECURITY
            "description": description or marker,
            "info": marker,
        }


ACTIVE_DIRECTORY = Dialect(
    name="ad",
    user_filter="(&(objectClass=user)(!(objectClass=computer))(!(sAMAccountName=*$)))",
    group_filter="(objectClass=group)",
    group_classes=("group",),
    user_classes=frozenset({"user", "person"}),
    id_attr="objectGUID",
    login_attr="sAMAccountName",
    upn_attr="userPrincipalName",
    group_login_attr="sAMAccountName",
    changed_attr="whenChanged",
    ou_filter="(|(objectClass=organizationalUnit)(objectClass=container))",
    sid_attr="objectSid",
    usn_attr="uSNChanged",
)

OPENLDAP = Dialect(
    name="openldap",
    user_filter="(|(objectClass=inetOrgPerson)(objectClass=posixAccount))",
    group_filter="(|(objectClass=groupOfNames)(objectClass=groupOfUniqueNames))",
    group_classes=("groupOfNames", "groupOfUniqueNames"),
    user_classes=frozenset({"inetorgperson", "posixaccount", "person"}),
    id_attr="entryUUID",
    login_attr="uid",
    upn_attr="mail",
    group_login_attr="cn",
    changed_attr="modifyTimestamp",
)


def of(params: dict[str, Any] | None) -> Dialect:
    return OPENLDAP if str((params or {}).get("directory_flavor") or "").strip().lower() == "openldap" else ACTIVE_DIRECTORY
