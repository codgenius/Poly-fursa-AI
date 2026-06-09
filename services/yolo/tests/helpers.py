"""
Shared test helper functions
"""
import sqlite3
import app as app_module


def insert_test_data(uid: str, timestamp: str, labels_with_scores: list):
    """
    Helper function to insert test data into the database.
    
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
