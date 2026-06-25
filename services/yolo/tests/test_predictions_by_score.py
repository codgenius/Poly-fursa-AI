"""
Tests for GET /predictions/score/{min_score} endpoint
"""
import pytest
from .helpers import insert_test_data


def test_get_predictions_by_score_happy_path(client, db):
    """Test getting predictions above confidence threshold"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.95), ("person", 0.87)], db=db)
    insert_test_data("session-2", "2024-01-02", [("car", 0.45), ("dog", 0.72)], db=db)
    
    response = client.get("/predictions/score/0.8")
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    assert len(data) == 2  # car(0.95) and person(0.87)
    # All returned scores should be >= 0.8
    for obj in data:
        assert obj["score"] >= 0.8
        assert obj["label"] in ["car", "person"]


def test_get_predictions_by_score_empty_result(client, db):
    """Test high threshold returns empty list"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.45)], db=db)
    
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


def test_get_predictions_by_score_boundary_zero(client, db):
    """Test score = 0.0 (lowest boundary)"""
    insert_test_data("session-1", "2024-01-01", [("car", 0.01), ("person", 0.99)], db=db)
    
    response = client.get("/predictions/score/0.0")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # All objects should be >= 0.0


def test_get_predictions_by_score_boundary_one(client, db):
    """Test score = 1.0 (highest boundary)"""
    insert_test_data("session-1", "2024-01-01", [("car", 1.0)], db=db)
    
    response = client.get("/predictions/score/1.0")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["score"] == 1.0
