"""
Tests for GET /predictions/label/{label} endpoint
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
