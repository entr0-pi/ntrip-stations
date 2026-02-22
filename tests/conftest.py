"""Pytest configuration and shared fixtures for testing."""

import os
import tempfile
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app import models, crud


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    db_fd, db_path = tempfile.mkstemp()
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    # Seed countries
    crud.seed_countries(db)

    yield db

    # Clean up database
    db.close()
    try:
        os.close(db_fd)
    except OSError:
        pass

    # Try to remove the file, but ignore failures (Windows file locks)
    try:
        os.unlink(db_path)
    except (OSError, PermissionError):
        pass


@pytest.fixture
def client(temp_db):
    """Create a FastAPI test client with a temporary database."""
    def override_get_db():
        yield temp_db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
