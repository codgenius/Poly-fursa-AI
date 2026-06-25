"""
Tests for GET /prediction/{uid} endpoint
"""
import uuid
import tempfile
import os
import pytest
from .helpers import insert_test_data
from models import PredictionSession, DetectionObject


def test_get_prediction_by_uid_happy_path(client, db):
    """Test retrieving a specific prediction session"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95), ("person", 0.87)], db=db)
    
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


def test_get_prediction_by_uid_no_objects(client, db):
    """Test prediction session with no detection objects"""
    prediction_session = PredictionSession(
        uid="session-empty",
        timestamp="2024-01-01",
        original_image="original.jpg",
        predicted_image="predicted.jpg"
    )
    db.add(prediction_session)
    db.commit()
    
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


def test_get_prediction_image_missing_file(client, db):
    """Test /prediction/{uid}/image returns 404 when file path doesn't exist on disk"""
    uid = str(uuid.uuid4())
    prediction_session = PredictionSession(
        uid=uid,
        original_image="/fake/path.jpg",
        predicted_image="/nonexistent/file.jpg"
    )
    db.add(prediction_session)
    db.commit()
    
    response = client.get(f"/prediction/{uid}/image")
    assert response.status_code == 404
    assert "Image not found" in response.json()["detail"]


def test_get_prediction_image_success(client, db):
    """Test /prediction/{uid}/image returns file successfully when it exists on disk"""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jpg', delete=False) as f:
        f.write("fake image content")
        temp_file_path = f.name
    
    try:
        uid = str(uuid.uuid4())
        # Insert prediction session pointing to the temporary file
        prediction_session = PredictionSession(
            uid=uid,
            original_image="/fake/original.jpg",
            predicted_image=temp_file_path
        )
        db.add(prediction_session)
        db.commit()
        
        # Get the image and verify it returns successfully
        response = client.get(f"/prediction/{uid}/image")
        assert response.status_code == 200
        # Verify we get file content back
        assert response.content == b"fake image content"
    finally:
        # Cleanup: remove temporary file
        os.unlink(temp_file_path)
