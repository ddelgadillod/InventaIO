"""
InventAI/o — Database session (SQLAlchemy)
Provides get_db dependency for FastAPI routes.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from core.config import get_settings

settings = get_settings()
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=settings.DB_POOL_SIZE,
                       max_overflow=settings.DB_MAX_OVERFLOW)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a DB session, closes on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
