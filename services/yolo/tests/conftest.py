"""
Shared pytest configuration and fixtures for all tests.
See CONFTEST_EXPLAINED.md for detailed explanation.
"""
import os
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add the parent directory to the path to import app
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as app_module
from app import app, init_db
from models import Base
from db import get_db
from tests.helpers import set_test_session


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """Set up in-memory database for each test. See CONFTEST_EXPLAINED.md for details."""
    # Create in-memory SQLite database for testing
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    Base.metadata.create_all(bind=engine)
    
    # Create a session for this test
    db = TestingSessionLocal()
    set_test_session(db)
    
    def override_get_db():
        try:
            yield db
        finally:
            pass  # Don't close db yet, it's needed for cleanup
    
    app.dependency_overrides[get_db] = override_get_db
    
    yield db  # TEST RUNS HERE
    
    # Cleanup
    db.close()
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """FastAPI TestClient for testing API endpoints. See CONFTEST_EXPLAINED.md for details."""
    return TestClient(app)
