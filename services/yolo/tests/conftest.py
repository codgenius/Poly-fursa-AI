"""
Shared pytest configuration and fixtures for all tests.
This file is auto-discovered by pytest and fixtures are available to all test files.
"""
import os
import sqlite3
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CONFIDENCE_THRESHOLD", "0.5")

import app as app_module
from app import app, init_db


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """
    Fixture to set up a temporary database for each test.
    autouse=True means it runs automatically for every test.
    """
    db_file = str(tmp_path / "test_predictions.db")
    monkeypatch.setattr("app.DB_PATH", db_file)
    init_db()


@pytest.fixture
def client():
    """Fixture that provides a TestClient for making requests to the API."""
    return TestClient(app)
