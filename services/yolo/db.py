import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import Base

# Ensure data directory exists (for SQLite database file)
os.makedirs("./data", exist_ok=True)

# Database configuration from environment variables
DB_BACKEND = os.environ.get("DB_BACKEND", "sqlite").lower()
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "predictions")

# Construct database URL
if DB_BACKEND == "postgres":
    DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    DATABASE_URL = "sqlite:///./data/predictions.db"

# Create engine with appropriate settings
if DB_BACKEND == "postgres":
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    # SQLite needs check_same_thread=False for threading
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency for getting a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
