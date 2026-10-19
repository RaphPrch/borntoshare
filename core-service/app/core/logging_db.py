from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Dedicated engine for borntoshare_logging (audit trail)
logging_engine = create_engine(
    settings.logging_sqlalchemy_url,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
)

LoggingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=logging_engine)
