"""
Tests for GET /prediction/{uid} endpoint
"""
import sqlite3
import app as app_module


def insert_test_data(uid: str, timestamp: str, labels_with_scores: list):
    """Helper to insert test data into DB"""
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
