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

# Construct database URL
if DB_BACKEND == "postgres":
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    # Default to SQLite
    DATABASE_URL = f"sqlite:///{DB_NAME}.db"

# Create engine with appropriate settings
if DB_BACKEND == "postgres":
    engine = create_engine(DATABASE_URL)
else:
    # SQLite needs check_same_thread=False for threading
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency for getting a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize the database by creating all tables."""
    Base.metadata.create_all(bind=engine)
