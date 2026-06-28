"""
Regression tests for the SQLAlchemy refactor.
These tests verify that the migration from raw sqlite3 to SQLAlchemy
preserved all data layer functionality and didn't break existing behavior.
"""
import pytest
from models import PredictionSession, DetectionObject


def test_database_session_is_functional():
    """
    Regression test: Verify that get_db() provides usable SQLAlchemy sessions.
    This tests the core database dependency injection added by the refactor.
    """
    from db import get_db
    
    # Create a session using the get_db dependency
    db_gen = get_db()
    session = next(db_gen)
    
    try:
        # Verify all essential SQLAlchemy session methods are available
        assert callable(session.query)
        assert callable(session.add)
        assert callable(session.commit)
        assert callable(session.close)
        assert callable(session.flush)
    finally:
        # Cleanup: trigger finally block
        try:
            next(db_gen)
        except StopIteration:
            pass


def test_prediction_session_orms_correctly(setup_db):
    """
    Regression test: Verify that PredictionSession ORM model works with database.
    Tests that the models.py refactor correctly represents the original schema.
    """
    db = setup_db
    
    # Create and save a PredictionSession
    session_data = PredictionSession(
        uid="test-uid-123",
        original_image="path/to/original.jpg",
        predicted_image="path/to/predicted.jpg"
    )
    db.add(session_data)
    db.commit()
    db.refresh(session_data)
    
    # Verify data was persisted
    retrieved = db.query(PredictionSession).filter_by(uid="test-uid-123").first()
    assert retrieved is not None
    assert retrieved.uid == "test-uid-123"
    assert retrieved.original_image == "path/to/original.jpg"
    assert retrieved.predicted_image == "path/to/predicted.jpg"


def test_detection_object_orms_correctly(setup_db):
    """
    Regression test: Verify that DetectionObject ORM model works with database.
    Tests that detection object storage via SQLAlchemy works correctly.
    """
    db = setup_db
    
    # Create a prediction session first
    session_data = PredictionSession(
        uid="test-uid-456",
        original_image="orig.jpg",
        predicted_image="pred.jpg"
    )
    db.add(session_data)
    db.flush()
    
    # Create detection objects
    detection1 = DetectionObject(
        prediction_uid="test-uid-456",
        label="car",
        score=0.95,
        box="[100, 200, 300, 400]"
    )
    detection2 = DetectionObject(
        prediction_uid="test-uid-456",
        label="person",
        score=0.87,
        box="[50, 60, 150, 250]"
    )
    db.add_all([detection1, detection2])
    db.commit()
    
    # Verify objects were persisted
    detections = db.query(DetectionObject).filter_by(prediction_uid="test-uid-456").all()
    assert len(detections) == 2
    labels = {d.label for d in detections}
    assert labels == {"car", "person"}
    scores = {d.score for d in detections}
    assert scores == {0.95, 0.87}


def test_hello_endpoint(client):
    """Verify /hello endpoint works (uncovered in original tests)."""
    response = client.get("/hello")
    assert response.status_code == 200
    assert response.json() == {"status": "hello there"}


def test_ready_endpoint(client):
    """Verify /ready endpoint works (uncovered signal handling path not tested)."""
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
