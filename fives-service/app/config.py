"""Settings of the module, from its environment (podman-compose gives it only what it reads)."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    INTERNAL_TOKEN: str = Field(min_length=1)
    # The core of BornToShare: the folders, the license, the identity of the person (internal API)
    B2S_CORE_URL: str = "http://core-service:8000"
    # Its own databases, on the MariaDB server of BornToShare, with its own account (rights on them only)
    FIVES_DB_HOST: str = "localhost"
    FIVES_DB_PORT: int = 3306
    FIVES_DB_USER: str = "b2s_fives"
    FIVES_DB_PASSWORD: str = ""
    FIVES_DB_NAME: str = "b2s_fives"
    FIVES_INVENTORY_DB_NAME: str = "b2s_fives_inventory"
    # How long the answer of the core about the license is kept (seconds)
    LICENSE_CACHE_SECONDS: int = 30


settings = Settings()
