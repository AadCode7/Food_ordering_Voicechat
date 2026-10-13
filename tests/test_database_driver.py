"""Regression tests for the PostgreSQL DBAPI required by SQLAlchemy 2.1."""
from sqlalchemy import create_engine


def test_postgresql_psycopg_driver_can_initialize_engine():
    # Vercel's DATABASE_URL may explicitly use postgresql+psycopg://.
    engine = create_engine(
        "postgresql+psycopg://user:password@localhost:5432/test",
        pool_pre_ping=True,
    )
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_default_postgresql_url_can_initialize_engine():
    # SQLAlchemy 2.1's default PostgreSQL driver is psycopg (v3).
    engine = create_engine("postgresql://user:password@localhost:5432/test")
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()
