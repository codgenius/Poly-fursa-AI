from sqlalchemy import Column, String, DateTime, Float, Text, Integer, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class PredictionSession(Base):
    """SQLAlchemy model for prediction sessions"""
    __tablename__ = "prediction_sessions"
    
    uid = Column(String, primary_key=True)
    timestamp = Column(String, default=lambda: datetime.utcnow().isoformat())
    original_image = Column(String)
    predicted_image = Column(String)
    
    # Relationship to detection objects
    detection_objects = relationship("DetectionObject", back_populates="prediction_session", cascade="all, delete-orphan")


class DetectionObject(Base):
    """SQLAlchemy model for detection objects"""
    __tablename__ = "detection_objects"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    prediction_uid = Column(String, ForeignKey("prediction_sessions.uid"))
    label = Column(String)
    score = Column(Float)
    box = Column(Text)
    
    # Relationship to prediction session
    prediction_session = relationship("PredictionSession", back_populates="detection_objects")
