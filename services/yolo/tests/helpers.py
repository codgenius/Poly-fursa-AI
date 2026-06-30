"""
Shared test helper functions
"""
from datetime import datetime
from models import PredictionSession, DetectionObject
import app as app_module

# Global session for test helpers
_test_session = None


def set_test_session(db):
    """Set the database session for test helpers to use."""
    global _test_session
    _test_session = db


def insert_test_data(uid: str, timestamp: str, labels_with_scores: list):
    """
    Helper function to insert test data into the database.
    
    Args:
        uid: prediction session ID
        timestamp: prediction timestamp (as string in YYYY-MM-DD format, converted to datetime)
        labels_with_scores: list of (label, score) tuples
    
    Example:
        insert_test_data("session-1", "2024-01-01", [("car", 0.95), ("person", 0.87)])
    """
    if _test_session is None:
        raise RuntimeError("Test session not set. Call set_test_session() first.")
    
    # Convert timestamp string to datetime object
    try:
        dt = datetime.strptime(timestamp, "%Y-%m-%d")
    except (ValueError, TypeError):
        dt = datetime.now()
    
    # Create prediction session
    prediction_session = PredictionSession(
        uid=uid,
        timestamp=dt,
        original_image="original.jpg",
        predicted_image="predicted.jpg"
    )
    _test_session.add(prediction_session)
    _test_session.flush()
    
    # Create detection objects
    for label, score in labels_with_scores:
        detection = DetectionObject(
            prediction_uid=uid,
            label=label,
            score=score,
            box="[0,0,100,100]"
        )
        _test_session.add(detection)
    
    _test_session.commit()
