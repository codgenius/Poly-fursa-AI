"""
Shared pytest configuration and fixtures for all tests.
This file is auto-discovered by pytest and fixtures are available to all test files.
"""
import os
import sqlite3
import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app, init_db

@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """
    Fixture to set up an in-memory database for each test.
    autouse=True means this runs AUTOMATICALLY before every single test without needing to request it.
    
    WHY monkeypatch?
    ---------------
    monkeypatch is a pytest feature that lets us TEMPORARILY replace variables in modules.
    It automatically reverts changes after each test. Think of it like a temporary edit that cleans itself up.
    
    WHAT does this fixture do?
    --------------------------
    1. Creates an in-memory SQLite database (file:memdb?mode=memory&cache=shared)
       - "memory" = stores in RAM, not on disk (FAST)
       - "cache=shared" = all connections in the same Python process see the same database
    
    2. Patches (replaces) sqlite3.connect function globally so it knows to add uri=True parameter
       when connecting to our test database
    
    3. Patches app.DB_PATH to point to the in-memory database instead of "predictions.db"
    
    4. Creates keeper_conn - a connection that stays open to keep the in-memory database alive
       (if all connections close, SQLite destroys in-memory databases)
    
    5. Runs the test (yield)
    
    6. Cleans up by dropping all tables (for test isolation - next test starts fresh)
    
    7. Closes keeper_conn
    """
    
    db_file = "file:memdb?mode=memory&cache=shared"
    
    # Store the REAL sqlite3.connect function before we replace it
    real_connect = sqlite3.connect
    
    # Define a wrapper function that will replace sqlite3.connect
    # This function is "nested" (defined inside setup_db) because it needs access to db_file
    def patched_connect(database, *args, **kwargs):
        """
        This function replaces the normal sqlite3.connect function.
        
        What it does:
        - If code tries to connect to our test database (db_file), 
          automatically add uri=True parameter
        - Otherwise, call the real sqlite3.connect unchanged
        
        Why? SQLite needs uri=True to understand the special URI syntax:
        file:memdb?mode=memory&cache=shared
        """
        if database == db_file:
            kwargs["uri"] = True
        return real_connect(database, *args, **kwargs)
    
    # Replace app.DB_PATH and sqlite3.connect with our test versions
    # monkeypatch will revert these after the test finishes
    monkeypatch.setattr("app.DB_PATH", db_file)
    monkeypatch.setattr(sqlite3, "connect", patched_connect)
    
    # Create and keep open a connection to prevent the in-memory database from being destroyed
    # (SQLite destroys in-memory databases when the last connection closes)
    keeper_conn = sqlite3.connect(db_file, uri=True)
    
    # Create the tables (CREATE TABLE IF NOT EXISTS, so safe to run multiple times)
    init_db()
    
    # yield means: pause here, run the test, then resume at the line after yield
    # Everything before yield = SETUP (runs before test)
    # Everything after yield = TEARDOWN (runs after test, cleanup)
    # This is how pytest fixtures work!
    
    yield  # <-- TEST RUNS HERE
    
    # CLEANUP: Drop all tables after test completes (test isolation)
    # Why? So the NEXT test starts with an empty database, not leftover data from previous test
    # This prevents tests from interfering with each other
    with sqlite3.connect(db_file, uri=True) as conn:
        conn.execute("DROP TABLE IF EXISTS detection_objects")
        conn.execute("DROP TABLE IF EXISTS prediction_sessions")
        conn.commit()
    
    # Close the keeper connection to release resources
    # After this line, monkeypatch automatically reverts our changes:
    # - DB_PATH goes back to "predictions.db"
    # - sqlite3.connect goes back to the real function
    keeper_conn.close()


@pytest.fixture
def client():
    """
    Fixture that provides a TestClient for making requests to the API.
    
    What is TestClient?
    - It's a FastAPI testing utility that lets us call API endpoints without starting a server
    - We can use it like: client.get("/health"), client.post("/predict", ...)
    - It returns a Response object with status_code, json(), etc.
    
    This fixture is NOT autouse, so you have to REQUEST it in your test:
    def test_something(client):  # <-- client fixture is injected here
        response = client.get("/health")
    """
    return TestClient(app)
