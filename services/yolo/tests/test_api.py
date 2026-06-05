import os
import sqlite3
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CONFIDENCE_THRESHOLD", "0.5")

import app as app_module
from app import app, init_db

TEST_IMAGE = os.path.join(os.path.dirname(__file__), "data", "beatles.jpeg")


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_predictions.db")
    monkeypatch.setattr("app.DB_PATH", db_file)
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def insert_test_data(uid: str, timestamp: str, labels_with_scores: list):
    """
    Helper to insert test data into DB.
    
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


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ============= GET /predictions/label/{label} TESTS =============

def test_get_predictions_by_label_happy_path(client):
    """Test getting predictions with a specific label (cars)"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95), ("person", 0.87)])
    insert_test_data("session-2", "2024-01-02", [("car", 0.92)])
    
    response = client.get("/predictions/label/car")
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    assert len(data) == 2
    # Check first session has car in detection_objects
    assert any(obj["label"] == "car" for obj in data[0]["detection_objects"])
    # Make sure person is NOT in results (should only be cars)
    assert not any(obj["label"] == "person" for session in data for obj in session["detection_objects"])


def test_get_predictions_by_label_empty_result(client):
    """Test label that doesn't exist returns empty list"""
    insert_test_data("session-1", "2024-01-01", [("person", 0.87)])
    
    response = client.get("/predictions/label/dog")
    assert response.status_code == 200
    assert response.json() == []


def test_get_predictions_by_label_empty_string(client):
    """Test empty label returns 400 error"""
    response = client.get("/predictions/label/")
    assert response.status_code == 404  # FastAPI treats empty path as no param


def test_get_predictions_by_label_single_object(client):
    """Test label with only one object in session"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95)])
    
    response = client.get("/predictions/label/car")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert len(data[0]["detection_objects"]) == 1
    assert data[0]["detection_objects"][0]["label"] == "car"
    assert data[0]["detection_objects"][0]["score"] == 0.95


# ============= GET /predictions/score/{min_score} TESTS =============

def test_get_predictions_by_score_happy_path(client):
    """Test getting predictions above confidence threshold"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95), ("person", 0.87)])
    insert_test_data("session-2", "2024-01-02", [("car", 0.45), ("dog", 0.72)])
    
    response = client.get("/predictions/score/0.8")
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    assert len(data) == 2  # car(0.95) and person(0.87)
    # All returned scores should be >= 0.8
    for obj in data:
        assert obj["score"] >= 0.8
        assert obj["label"] in ["car", "person"]


def test_get_predictions_by_score_empty_result(client):
    """Test high threshold returns empty list"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.45)])
    
    response = client.get("/predictions/score/0.9")
    assert response.status_code == 200
    assert response.json() == []


def test_get_predictions_by_score_invalid_low(client):
    """Test score < 0.0 returns 400"""
    response = client.get("/predictions/score/-0.1")
    assert response.status_code == 400
    assert "min_score must be between 0.0 and 1.0" in response.json()["detail"]


def test_get_predictions_by_score_invalid_high(client):
    """Test score > 1.0 returns 400"""
    response = client.get("/predictions/score/1.5")
    assert response.status_code == 400
    assert "min_score must be between 0.0 and 1.0" in response.json()["detail"]


def test_get_predictions_by_score_boundary_zero(client):
    """Test score = 0.0 (lowest boundary)"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.01), ("person", 0.99)])
    
    response = client.get("/predictions/score/0.0")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # All objects should be >= 0.0


def test_get_predictions_by_score_boundary_one(client):
    """Test score = 1.0 (highest boundary)"""
    insert_test_data("session-1", "2024-01-01", [("car", 1.0)])
    
    response = client.get("/predictions/score/1.0")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["score"] == 1.0


# ============= GET /prediction/{uid} TESTS =============

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


