"""
Tests for GET /predictions/score/{min_score} endpoint
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

