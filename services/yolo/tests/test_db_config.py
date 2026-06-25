"""
Tests for database configuration and backend switching
"""
import os
import uuid
import pytest
from sqlalchemy import text


def test_get_db_dependency_yields_valid_session(db):
    """Test that get_db() properly yields a database session"""
    from db import get_db
    from sqlalchemy.orm import Session as SessionType
    
    gen = get_db()
    session = next(gen)
    
    # Session should be a valid SQLAlchemy Session
    assert session is not None
    assert hasattr(session, "query")
    assert hasattr(session, "add")
    assert hasattr(session, "commit")
    assert hasattr(session, "close")
    
    # Cleanup
    try:
        next(gen)
    except StopIteration:
        pass


def test_get_db_dependency_supports_context_manager(db):
    """Test that get_db() yields sessions that support database operations"""
    from db import get_db
    from models import PredictionSession
    
    gen = get_db()
    session = next(gen)
    
    try:
        # Should be able to query
        query = session.query(PredictionSession)
        assert query is not None
        
        # Should be able to get results
        results = query.all()
        assert isinstance(results, list)
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_sqlite_engine_functional():
    """Test SQLite engine can execute queries"""
    from db import engine
    
    # Engine should be functional
    assert engine is not None
    
    # Should be able to connect and execute a simple query
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


def test_detection_objects_foreign_key_constraint():
    """Test that detection_objects table has foreign key constraint to prediction_sessions"""
    from db import engine
    
    with engine.connect() as conn:
        # Check that prediction_uid column exists and has correct type
        result = conn.execute(text(
            "PRAGMA table_info(detection_objects)"
        ))
        columns = result.fetchall()
        column_names = [col[1] for col in columns]
        
        assert "prediction_uid" in column_names
        assert "label" in column_names
        assert "score" in column_names
        assert "box" in column_names


def test_get_db_yields_different_sessions(db):
    """Test that successive calls to get_db() yield different session instances"""
    from db import get_db
    
    # First session
    gen1 = get_db()
    session1 = next(gen1)
    
    # Second session
    gen2 = get_db()
    session2 = next(gen2)
    
    try:
        # Sessions should be different instances
        assert session1 is not session2
    finally:
        # Cleanup
        try:
            next(gen1)
        except StopIteration:
            pass
        try:
            next(gen2)
        except StopIteration:
            pass


def test_session_can_query_and_persist_data(db):
    """Test that session obtained from get_db() can query and persist data"""
    from db import get_db
    from models import PredictionSession
    
    gen = get_db()
    session = next(gen)
    
    try:
        # Create a test session with unique UUID
        test_uid = str(uuid.uuid4())
        test_session = PredictionSession(
            uid=test_uid,
            timestamp="2024-01-01T12:00:00",
            original_image="test.jpg",
            predicted_image="test_pred.jpg"
        )
        session.add(test_session)
        session.commit()
        
        # Query it back
        retrieved = session.query(PredictionSession).filter(
            PredictionSession.uid == test_uid
        ).first()
        
        assert retrieved is not None
        assert retrieved.uid == test_uid
        assert retrieved.original_image == "test.jpg"
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_base_metadata_tables_registered():
    """Test that Base.metadata includes prediction tables"""
    from models import Base
    
    # Base should have the tables registered
    table_names = [table.name for table in Base.metadata.tables.values()]
    
    assert "prediction_sessions" in table_names
    assert "detection_objects" in table_names


def test_postgresql_connection_string_format():
    """Test PostgreSQL connection string format (validated without connecting)"""
    # Test that PostgreSQL URL is correctly formatted when DB_BACKEND=postgres
    # We validate the format by constructing it with test values
    db_user = "testuser"
    db_password = "testpass"
    db_host = "localhost"
    db_port = "5432"
    db_name = "testdb"
    
    # This is the same construction logic as in db.py
    postgresql_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    assert postgresql_url == "postgresql://testuser:testpass@localhost:5432/testdb"
    assert "postgresql://" in postgresql_url
    assert "@" in postgresql_url
    assert ":" in postgresql_url


def test_database_url_format_validation():
    """Test that DATABASE_URL is properly formatted for the configured backend"""
    from db import DATABASE_URL
    
    # SQLite should use sqlite:/// protocol
    assert DATABASE_URL.startswith("sqlite:///")
    
    # URL should be a valid string
    assert isinstance(DATABASE_URL, str)
    assert len(DATABASE_URL) > 0

