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
from unittest.mock import patch

# Set AWS environment variables before any imports
os.environ["AWS_REGION"] = "us-east-1"
os.environ["AWS_S3_BUCKET"] = "test-bucket"

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


@pytest.fixture(autouse=True)
def mock_s3_operations():
    """Mock S3 operations to avoid actual S3 calls during testing."""
    with patch("s3_utils.download_image_from_s3") as mock_download:
        with patch("s3_utils.upload_image_to_s3") as mock_upload:
            mock_upload.return_value = "chat_id/prediction_id/predicted/prediction_id.jpg"
            yield


@pytest.fixture
def client():
    """FastAPI TestClient for testing API endpoints. See CONFTEST_EXPLAINED.md for details."""
    return TestClient(app)
