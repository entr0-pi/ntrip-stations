"""SQLAlchemy database configuration for the RTK2GO Station Finder.

Sets up a SQLite database engine, session factory, and FastAPI dependency
for injecting database sessions into route handlers.
"""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Database file stored in project root
DB_PATH = Path(__file__).parent.parent / "rtk2go.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,  # Required for SQLite + FastAPI's async/threading model
        # By default SQLite enforces that database connections are used only in
        # the same thread. FastAPI uses different threads for handling requests,
        # so we disable this check. SQLite's locking is still thread-safe.
    }
)

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
