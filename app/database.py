"""SQLAlchemy database configuration for the RTK2GO Station Finder.

Sets up the database engine (SQLite by default, Postgres via DATABASE_URL), session factory, and FastAPI dependency
for injecting database sessions into route handlers.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import NullPool

load_dotenv()

# Default: SQLite file stored in project root (local dev / VM deployment).
# Set DATABASE_URL to use Postgres instead (required on Vercel, e.g. Neon).
DB_PATH = Path(__file__).parent.parent / "rtk2go.db"


def _normalize_database_url(url: str) -> str:
    """Make provider URLs (postgres://, postgresql://) use the psycopg 3 driver."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _normalize_database_url(os.getenv("DATABASE_URL") or f"sqlite:///{DB_PATH}")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={
            # SQLite only allows a connection in the thread that created it;
            # FastAPI handles requests across threads, so disable the check.
            "check_same_thread": False,
        },
    )
else:
    # Serverless-friendly: don't keep a client-side pool between invocations.
    # Use the provider's pooled connection URL (e.g. Neon "-pooler" host).
    engine = create_engine(DATABASE_URL, poolclass=NullPool)

# Session factory for creating database sessions
# autocommit=False: explicit commit() required
# autoflush=False: explicit flush() for write operations (cleaner control)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


def get_db():
    """FastAPI dependency: yields a database session per request.

    The session is automatically closed after the request completes,
    regardless of success or exception. This ensures resources are freed
    and connections are returned to the pool.

    Yields:
        SQLAlchemy Session instance for the request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
