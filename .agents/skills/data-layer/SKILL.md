# yolo-api-data-layer

## Description

Use this skill when working on the YOLO service API data layer, especially requests involving SQLAlchemy, database models, persistence, database-backed endpoints, tests for database behavior, or making the database backend configurable.

Example activating prompts:
- "refactor the api to use sqlalchemy"
- "use the yolo-api-data-layer skill to refactor the api to work with sqlalchemy"
- "add an endpoint GET /predictions/recent that returns the 10 most recent sessions"
- "add a UserFeedback table to track user ratings per prediction"
- "write tests for the /predict endpoint"
- "the database layer doesn't follow our architectural design, fix it"
- "delete a prediction session and all its detection objects by uid"
- "add a column processing_time_ms to the prediction_sessions table"
- "make the database backend configurable so we can use postgres in production"

## Goal

Refactor or extend the YOLO service database layer using SQLAlchemy while preserving the public API behavior.

The YOLO service currently stores prediction sessions and detection objects. The data layer must be moved away from raw `sqlite3` usage and raw SQL strings into SQLAlchemy models, sessions, and queries.

## Hard requirements

1. Preserve all existing endpoint paths, status codes, request formats, and response shapes unless the user explicitly asks for a new endpoint or new field.
2. Do not change frontend or agent behavior.
3. Do not remove existing YOLO prediction functionality.
4. Do not break image upload, image saving, annotated image saving, or prediction lookup.
5. Do not commit secrets, `.env`, AWS credentials, database passwords, generated databases, uploaded images, or local cache files.
6. Do not use raw `sqlite3` in the YOLO service after the refactor.
7. Do not use raw SQL strings for normal CRUD operations. Use SQLAlchemy ORM models and session queries.
8. Keep SQLite as the default development backend.
9. Support PostgreSQL through environment variables.
10. Run tests before claiming completion.

## Expected architecture

Create or update these files under `services/yolo/`:

- `models.py`
- `db.py`
- `app.py`
- `requirements.txt`
- relevant tests under `tests/` or the existing test directory

### `services/yolo/models.py`

Define SQLAlchemy ORM models for:

- `PredictionSession`
- `DetectionObject`

The models must represent the existing database tables:

`prediction_sessions`:
- `uid` primary key string
- `timestamp`
- `original_image`
- `predicted_image`

`detection_objects`:
- `id` integer primary key autoincrement
- `prediction_uid`
- `label`
- `score`
- `box`

Use a shared declarative `Base`.

Prefer a relationship between `PredictionSession` and `DetectionObject` when appropriate, but do not change response shapes because of relationships.

### `services/yolo/db.py`

Create the SQLAlchemy engine and session factory.

Use environment variables:

- `DB_BACKEND`, default `sqlite`
- `DB_USER`, default `user`
- `DB_PASSWORD`, default `pass`
- `DB_HOST`, default `localhost`
- `DB_PORT`, default `5432`
- `DB_NAME`, default `predictions`

Behavior:

- If `DB_BACKEND=postgres`, use PostgreSQL.
- Otherwise, use SQLite at `sqlite:///./predictions.db`.
- For SQLite, use `connect_args={"check_same_thread": False}`.
- Provide `SessionLocal`.
- Provide `get_db()` FastAPI dependency.
- Create tables with `Base.metadata.create_all(bind=engine)` on app startup or module initialization in a simple, reliable way.

### `services/yolo/app.py`

Refactor data access to use SQLAlchemy.

Use FastAPI dependency injection:

```python
from fastapi import Depends
from sqlalchemy.orm import Session
from .db import get_db