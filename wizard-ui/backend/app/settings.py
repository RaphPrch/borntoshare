import os

"""
BornToShare – Wizard Settings (V1)
---------------------------------

Le wizard gère deux modes :
  - dev  → exécute réellement la création DB/users/schema/admin
  - prod → ne touche pas la DB, produit un pack Ansible

Le wizard est volontairement simple :
- pas de session
- pas de Keycloak
- pas de CSRF
- pas de proxy
- lecture ENV uniquement
"""

MODE = os.getenv("WIZARD_MODE", "dev").lower()


def is_dev() -> bool:
    return MODE == "dev"


def is_prod() -> bool:
    return MODE == "prod"


# Compatibilité minimale si ancien code attend `settings`
class _SettingsProxy:
    MODE = MODE

    @staticmethod
    def is_dev() -> bool:
        return is_dev()

    @staticmethod
    def is_prod() -> bool:
        return is_prod()


settings = _SettingsProxy()
