"""Database setup for Postgres using SQLAlchemy.

This module defines the engine, session factory, and declarative base.
Tables are created automatically on app startup (see main.py).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config import get_settings


settings = get_settings()

# Example URL: postgresql+psycopg2://user:password@localhost:5432/call_routing
engine = create_engine(settings.DATABASE_URL, future=True)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


def get_db():
    """FastAPI dependency helper for DB sessions (not yet used in routes)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
