from __future__ import annotations

from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scanner import config


def _url(database: str) -> str:
    return f"mysql+pymysql://{quote_plus(config.DB_USER)}:{quote_plus(config.DB_PASSWORD)}@{config.DB_HOST}:{config.DB_PORT}/{database}?charset=utf8mb4"


engine = create_engine(_url(config.DB_NAME), pool_pre_ping=True, pool_recycle=1800)
inventory_engine = create_engine(_url(config.INVENTORY_DB_NAME), pool_pre_ping=True, pool_recycle=1800)
Session = sessionmaker(bind=engine, autoflush=False)
InventorySession = sessionmaker(bind=inventory_engine, autoflush=False)
