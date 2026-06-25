"""
Shared pytest configuration and fixtures for all tests.
See CONFTEST_EXPLAINED.md for detailed explanation.
"""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app import app
from db import get_db
from models import Base


# In-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

# Store the test engine and session factory globally for access in tests
test_engine = None
TestingSessionLocal = None


@pytest.fixture(scope="function")
def setup_db():
    """Set up in-memory database for each test. See CONFTEST_EXPLAINED.md for details."""
    global test_engine, TestingSessionLocal
    
    # Create engine with in-memory database
    test_engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Create all tables
    Base.metadata.create_all(bind=test_engine)
    
    # Create test session factory
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    # Override dependency
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    yield  # TEST RUNS HERE
    
    # Cleanup: drop all tables for isolation
    Base.metadata.drop_all(bind=test_engine)
    
    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
def db(setup_db) -> Session:
    """Provide a database session for tests that need direct database access."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(setup_db):
    """FastAPI TestClient for testing API endpoints. See CONFTEST_EXPLAINED.md for details."""
    return TestClient(app)
