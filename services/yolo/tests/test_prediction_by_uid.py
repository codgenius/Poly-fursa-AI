"""
Tests for GET /prediction/{uid} endpoint
"""
import sqlite3
import uuid
import tempfile
import os
import pytest
from .helpers import insert_test_data
import app as app_module


def test_get_prediction_by_uid_happy_path(client):
    """Test retrieving a specific prediction session"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95), ("person", 0.87)])
    
    response = client.get("/prediction/session-1")
    assert response.status_code == 200
    data = response.json()
    
    assert data["uid"] == "session-1"
    assert data["timestamp"] == "2024-01-01"
    assert len(data["detection_objects"]) == 2
    assert data["original_image"] == "original.jpg"
    assert data["predicted_image"] == "predicted.jpg"


def test_get_prediction_by_uid_not_found(client):
    """Test retrieving non-existent prediction returns 404"""
    response = client.get("/prediction/nonexistent")
    assert response.status_code == 404
    assert "Prediction not found" in response.json()["detail"]


def test_get_prediction_by_uid_no_objects(client):
    """Test prediction session with no detection objects"""
    with sqlite3.connect(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO prediction_sessions (uid, timestamp, original_image, predicted_image) VALUES (?, ?, ?, ?)",
            ("session-empty", "2024-01-01", "original.jpg", "predicted.jpg")
        )
        conn.commit()
    
    response = client.get("/prediction/session-empty")
    assert response.status_code == 200
    data = response.json()
    assert data["uid"] == "session-empty"
    assert data["detection_objects"] == []


def test_get_prediction_image_not_found(client):
    """Test /prediction/{uid}/image returns 404 for non-existent uid"""
    response = client.get("/prediction/nonexistent-uid/image")
    assert response.status_code == 404
    assert "Image not found" in response.json()["detail"]


def test_get_prediction_image_missing_file(client):
    """Test /prediction/{uid}/image returns 404 when file path doesn't exist on disk"""
    uid = str(uuid.uuid4())
    with sqlite3.connect(app_module.DB_PATH, uri=True) as conn:
        conn.execute("""
            INSERT INTO prediction_sessions (uid, original_image, predicted_image)
            VALUES (?, ?, ?)
        """, (uid, "/fake/path.jpg", "/nonexistent/file.jpg"))
        conn.commit()
    
    response = client.get(f"/prediction/{uid}/image")
    assert response.status_code == 404
    assert "Image not found" in response.json()["detail"]


def test_get_prediction_image_success(client):
    """Test /prediction/{uid}/image returns file successfully when it exists on disk"""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jpg', delete=False) as f:
        f.write("fake image content")
        temp_file_path = f.name
    
    try:
        uid = str(uuid.uuid4())
        # Insert prediction session pointing to the temporary file
        with sqlite3.connect(app_module.DB_PATH, uri=True) as conn:
            conn.execute("""
                INSERT INTO prediction_sessions (uid, original_image, predicted_image)
                VALUES (?, ?, ?)
            """, (uid, "/fake/original.jpg", temp_file_path))
            conn.commit()
        
        # Get the image and verify it returns successfully
        response = client.get(f"/prediction/{uid}/image")
        assert response.status_code == 200
        # Verify we get file content back
        assert response.content == b"fake image content"
    finally:
        # Cleanup: remove temporary file
        os.unlink(temp_file_path)
