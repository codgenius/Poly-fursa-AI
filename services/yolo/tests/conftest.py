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


def insert_test_data(uid: str, timestamp: str, labels_with_scores: list):
    """
    Helper function to insert test data into the database.
    
    Args:
        uid: prediction session ID
        timestamp: prediction timestamp
        labels_with_scores: list of (label, score) tuples
    
    Example:
        insert_test_data("session-1", "2024-01-01", [("car", 0.95), ("person", 0.87)])
    """
    with sqlite3.connect(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO prediction_sessions (uid, timestamp, original_image, predicted_image) VALUES (?, ?, ?, ?)",
            (uid, timestamp, "original.jpg", "predicted.jpg")
        )
        for label, score in labels_with_scores:
            conn.execute(
                "INSERT INTO detection_objects (prediction_uid, label, score, box) VALUES (?, ?, ?, ?)",
                (uid, label, score, "[0,0,100,100]")
            )
        conn.commit()
