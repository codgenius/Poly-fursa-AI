"""
Shared test helper functions
"""
from sqlalchemy.orm import Session
from models import PredictionSession, DetectionObject
from db import SessionLocal


def insert_test_data(uid: str, timestamp: str, labels_with_scores: list, db: Session = None):
    """
    Helper function to insert test data into the database.
    
    Args:
        uid: prediction session ID
        timestamp: prediction timestamp
        labels_with_scores: list of (label, score) tuples
        db: SQLAlchemy session (optional, creates new one if not provided)
    
    Example:
        insert_test_data("session-1", "2024-01-01", [("car", 0.95), ("person", 0.87)])
    """
    session = db if db else SessionLocal()
    try:
        # Insert prediction session
        prediction_session = PredictionSession(
            uid=uid,
            timestamp=timestamp,
            original_image="original.jpg",
            predicted_image="predicted.jpg"
        )
        session.add(prediction_session)
        session.flush()  # Ensure the session is added
        
        # Insert detection objects
        for label, score in labels_with_scores:
            detection_obj = DetectionObject(
                prediction_uid=uid,
                label=label,
                score=score,
                box="[0,0,100,100]"
            )
            session.add(detection_obj)
        
        session.commit()
    finally:
        if not db:  # Only close if we created the session
            session.close()

