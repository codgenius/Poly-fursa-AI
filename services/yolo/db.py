import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

# Database configuration from environment variables
DB_BACKEND = os.environ.get("DB_BACKEND", "sqlite")
DB_USER = os.environ.get("DB_USER", "user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "pass")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "predictions")

# Create database URL based on backend
if DB_BACKEND == "postgres":
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(DATABASE_URL)
else:
    # Default to SQLite
    DATABASE_URL = "sqlite:///./predictions.db"
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)


def get_db():
    """
    FastAPI dependency for database sessions
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
