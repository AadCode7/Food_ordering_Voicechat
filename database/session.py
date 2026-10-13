"""Engine + session factory. SQLite for local dev, Supabase Postgres in production."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from config import settings
from logger import get_logger

from .base import Base

log = get_logger("database")


def _database_url() -> str:
    url = settings.database_url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("sqlite") and os.getenv("VERCEL"):
        log.warning("SQLite on Vercel is ephemeral; set DATABASE_URL to Supabase Postgres.")
        url = "sqlite:////tmp/local.db"
    return url


def _make_engine():
    url = _database_url()
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    if os.getenv("VERCEL"):
        # Serverless: no long-lived pool; rely on Supabase's pooler (port 6543).
        return create_engine(url, poolclass=NullPool, pool_pre_ping=True)
    return create_engine(url, pool_size=5, max_overflow=5, pool_pre_ping=True, pool_recycle=1800)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from api.models import orm  # noqa: F401  (registers the tables)

    Base.metadata.create_all(bind=engine)
