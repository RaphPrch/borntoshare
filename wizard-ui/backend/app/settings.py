"""
BornToShare – Wizard Settings (V1)

Wizard execution modes:
- dev  → performs real DB / schema / admin creation
- prod → read-only mode, generates Ansible packs

Design goals:
- simple
- no session
- no auth
- no CSRF
- env-driven only
"""

from __future__ import annotations

import os


# ============================================================
# ⚙️ MODE RESOLUTION
# ============================================================
def get_mode() -> str:
    """
    Resolve wizard mode.

    Priority:
    - WIZARD_MODE
    - APP_ENV
    - default: dev
    """
    return os.getenv("WIZARD_MODE", os.getenv("APP_ENV", "dev")).lower()


def is_dev() -> bool:
    return get_mode() == "dev"


def is_prod() -> bool:
    return get_mode() == "prod"


# ============================================================
# 🔁 Legacy compatibility proxy
# ============================================================
class _SettingsProxy:
    """
    Minimal proxy for legacy code expecting `settings.MODE`
    and `settings.is_dev()`.
    """

    @property
    def MODE(self) -> str:
        return get_mode()

    @staticmethod
    def is_dev() -> bool:
        return is_dev()

    @staticmethod
    def is_prod() -> bool:
        return is_prod()


settings = _SettingsProxy()
