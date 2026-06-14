"""
Shared pytest configuration and fixtures for all tests.
See CONFTEST_EXPLAINED.md for detailed explanation.
"""
import os
import sqlite3
import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app, init_db


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """Set up in-memory database for each test. See CONFTEST_EXPLAINED.md for details."""
    db_file = "file:memdb?mode=memory&cache=shared"
    real_connect = sqlite3.connect
    
    def patched_connect(database, *args, **kwargs):
        if database == db_file:
            kwargs["uri"] = True
        return real_connect(database, *args, **kwargs)
    
    monkeypatch.setattr("app.DB_PATH", db_file)
    monkeypatch.setattr(sqlite3, "connect", patched_connect)
    
    keeper_conn = sqlite3.connect(db_file, uri=True)
    init_db()
    
    yield  # TEST RUNS HERE
    
    # Cleanup: drop tables for isolation
    with sqlite3.connect(db_file, uri=True) as conn:
        conn.execute("DROP TABLE IF EXISTS detection_objects")
        conn.execute("DROP TABLE IF EXISTS prediction_sessions")
        conn.commit()
    
    keeper_conn.close()


@pytest.fixture
def client():
    """FastAPI TestClient for testing API endpoints. See CONFTEST_EXPLAINED.md for details."""
    return TestClient(app)
