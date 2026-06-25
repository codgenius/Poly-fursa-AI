"""
Tests for GET /predictions/label/{label} endpoint
"""
import pytest
from .helpers import insert_test_data


def test_get_predictions_by_label_happy_path(client, db):
    """Test getting predictions with a specific label (cars)"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95), ("person", 0.87)], db=db)
    insert_test_data("session-2", "2024-01-02", [("car", 0.92)], db=db)
    
    response = client.get("/predictions/label/car")
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    assert len(data) == 2
    # Check first session has car in detection_objects
    assert any(obj["label"] == "car" for obj in data[0]["detection_objects"])
    # Make sure person is NOT in results (should only be cars)
    assert not any(obj["label"] == "person" for session in data for obj in session["detection_objects"])


def test_get_predictions_by_label_empty_result(client, db):
    """Test label that doesn't exist returns empty list"""
    insert_test_data("session-1", "2024-01-01", [("person", 0.87)], db=db)
    
    response = client.get("/predictions/label/dog")
    assert response.status_code == 200
    assert response.json() == []


def test_get_predictions_by_label_empty_string(client):
    """Test empty label returns 404 (FastAPI routing doesn't match empty path)"""
    response = client.get("/predictions/label/")
    assert response.status_code == 404  # FastAPI treats empty path as no route match


def test_get_predictions_by_label_single_object(client, db):
    """Test label with only one object in session"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95)], db=db)
    
    response = client.get("/predictions/label/car")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert len(data[0]["detection_objects"]) == 1
    assert data[0]["detection_objects"][0]["label"] == "car"
    assert data[0]["detection_objects"][0]["score"] == 0.95


def test_get_predictions_by_label_multiple_objects_same_label(client, db):
    """Test session with multiple objects of the same label"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95), ("car", 0.88), ("person", 0.85)], db=db)
    
    response = client.get("/predictions/label/car")
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) == 1
    cars = data[0]["detection_objects"]
    assert len(cars) == 2
    # Verify only cars are returned
    assert all(obj["label"] == "car" for obj in cars)
    # Verify scores are preserved
    car_scores = sorted([obj["score"] for obj in cars])
    assert car_scores == [0.88, 0.95]


def test_get_predictions_by_label_response_structure(client, db):
    """Test response structure contains all required fields"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95)], db=db)
    
    response = client.get("/predictions/label/car")
    assert response.status_code == 200
    data = response.json()
    
    session = data[0]
    # Verify session fields
    assert "uid" in session
    assert "timestamp" in session
    assert "original_image" in session
    assert "predicted_image" in session
    assert "detection_objects" in session
    
    # Verify detection object fields
    obj = session["detection_objects"][0]
    assert "id" in obj
    assert "label" in obj
    assert "score" in obj
    assert "box" in obj


def test_get_predictions_by_label_multiple_sessions_same_label(client, db):
    """Test multiple sessions with same label returns all sessions"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95)], db=db)
    insert_test_data("session-2", "2024-01-02", [("car", 0.87)], db=db)
    insert_test_data("session-3", "2024-01-03", [("person", 0.90)], db=db)
    
    response = client.get("/predictions/label/car")
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) == 2
    uids = [session["uid"] for session in data]
    assert "session-1" in uids
    assert "session-2" in uids
    assert "session-3" not in uids


def test_get_predictions_by_label_filters_by_exact_label(client, db):
    """Test that only exact label matches are returned, not partial matches"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95)], db=db)
    insert_test_data("session-2", "2024-01-02", [("car_small", 0.87)], db=db)
    insert_test_data("session-3", "2024-01-03", [("carpark", 0.90)], db=db)
    
    response = client.get("/predictions/label/car")
    assert response.status_code == 200
    data = response.json()
    
    # Should only return session-1
    assert len(data) == 1
    assert data[0]["uid"] == "session-1"
    assert all(obj["label"] == "car" for obj in data[0]["detection_objects"])


def test_get_predictions_by_label_special_characters(client, db):
    """Test label with special characters"""
    insert_test_data("session-1", "2024-01-01", [("car-white", 0.95)], db=db)
    insert_test_data("session-2", "2024-01-02", [("car_blue", 0.88)], db=db)
    insert_test_data("session-3", "2024-01-03", [("car.small", 0.85)], db=db)
    
    # Test hyphen
    response = client.get("/predictions/label/car-white")
    assert response.status_code == 200
    assert len(response.json()) == 1
    
    # Test underscore
    response = client.get("/predictions/label/car_blue")
    assert response.status_code == 200
    assert len(response.json()) == 1
    
    # Test dot
    response = client.get("/predictions/label/car.small")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_predictions_by_label_case_sensitive(client, db):
    """Test that label matching is case-sensitive"""
    insert_test_data("session-1", "2024-01-01", [("Car", 0.95)], db=db)
    insert_test_data("session-2", "2024-01-02", [("CAR", 0.88)], db=db)
    
    # Search for lowercase "car" - should not match "Car" or "CAR"
    response = client.get("/predictions/label/car")
    assert response.status_code == 200
    assert len(response.json()) == 0
    
    # Search for "Car" - should match only session-1
    response = client.get("/predictions/label/Car")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_predictions_by_label_numeric_label(client, db):
    """Test label that is numeric string"""
    insert_test_data("session-1", "2024-01-01", [("123", 0.95)], db=db)
    insert_test_data("session-2", "2024-01-02", [("456", 0.88)], db=db)
    
    response = client.get("/predictions/label/123")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["detection_objects"][0]["label"] == "123"


def test_get_predictions_by_label_sql_injection_attempt(client, db):
    """Test that SQL injection attempts are safely handled"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95)], db=db)
    
    # Try various SQL injection patterns
    malicious_labels = [
        "car'; DROP TABLE prediction_sessions; --",
        "car' OR '1'='1",
        "car\" UNION SELECT * FROM prediction_sessions --",
    ]
    
    for malicious_label in malicious_labels:
        response = client.get(f"/predictions/label/{malicious_label}")
        # Should return 200 with empty result (safe handling via parameterized queries)
        assert response.status_code == 200
        assert response.json() == []
    
    # Verify data integrity - original data should still exist
    response = client.get("/predictions/label/car")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_predictions_by_label_very_long_label(client, db):
    """Test with very long label string"""
    long_label = "a" * 1000
    insert_test_data("session-1", "2024-01-01", [(long_label, 0.95)], db=db)
    
    response = client.get(f"/predictions/label/{long_label}")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_predictions_by_label_url_encoded_characters(client, db):
    """Test label with characters that might need URL encoding"""
    # Spaces are handled by URL encoding
    insert_test_data("session-1", "2024-01-01", [("car model", 0.95)], db=db)
    
    response = client.get("/predictions/label/car%20model")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["detection_objects"][0]["label"] == "car model"


def test_get_predictions_by_label_timestamp_preserved(client, db):
    """Test that timestamp is correctly returned in response"""
    insert_test_data("session-1", "2024-01-01 10:30:00", [("car", 0.95)], db=db)
    insert_test_data("session-2", "2024-01-02 15:45:30", [("car", 0.87)], db=db)
    
    response = client.get("/predictions/label/car")
    assert response.status_code == 200
    data = response.json()
    
    timestamps = [session["timestamp"] for session in data]
    assert "2024-01-01 10:30:00" in timestamps
    assert "2024-01-02 15:45:30" in timestamps


def test_get_predictions_by_label_image_paths_preserved(client, db):
    """Test that image paths are correctly preserved in response"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95)], db=db)
    
    response = client.get("/predictions/label/car")
    assert response.status_code == 200
    data = response.json()
    
    session = data[0]
    assert session["original_image"] == "original.jpg"
    assert session["predicted_image"] == "predicted.jpg"


def test_get_predictions_by_label_score_accuracy(client, db):
    """Test that all scores are accurately preserved"""
    test_scores = [0.99, 0.5, 0.1, 0.999, 0.0]
    labels_with_scores = [(f"obj-{i}", score) for i, score in enumerate(test_scores)]
    insert_test_data("session-1", "2024-01-01", labels_with_scores, db=db)
    
    for i, score in enumerate(test_scores):
        response = client.get(f"/predictions/label/obj-{i}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        returned_score = data[0]["detection_objects"][0]["score"]
        # Check score with small float tolerance
        assert abs(returned_score - score) < 0.0001
