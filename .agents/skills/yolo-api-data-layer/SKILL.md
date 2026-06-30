---
name: yolo-api-data-layer
description: Use this skill whenever modifying the YOLO service data layer, database models, persistence, database-backed endpoints, or database configuration. Use SQLAlchemy ORM for all database operations and avoid introducing raw sqlite3 or raw SQL CRUD operations.
---

# yolo-api-data-layer

## Purpose

Use this skill whenever working on the YOLO service data layer.

The YOLO service must use SQLAlchemy for database access. Do not introduce raw `sqlite3` usage or raw SQL CRUD logic.

## Goal

Maintain and extend the YOLO service data layer using SQLAlchemy.

Whenever database-related functionality is modified, preserve the existing architecture by using SQLAlchemy ORM models, sessions, and dependency injection instead of raw SQLite operations.

The goal is to keep the data layer database-agnostic so the service works with both SQLite (development) and PostgreSQL (production) without changing application behavior.

## Scope

Apply this skill when a change touches:

- database models
- prediction session persistence
- detection object persistence
- database-backed API endpoints
- database configuration
- SQLite/PostgreSQL backend behavior
- tests for database behavior

Only implement the user's requested change. Do not add unrelated endpoints, tables, columns, or response fields.

## Architecture requirements

The YOLO service data layer should use:

- SQLAlchemy ORM models
- a shared declarative `Base`
- `SessionLocal`
- `get_db()` dependency
- FastAPI `Depends(get_db)` where appropriate
- SQLite as the default local backend
- PostgreSQL support through environment variables

Expected core files:

- `services/yolo/models.py`
- `services/yolo/db.py`
- `services/yolo/app.py`
- `services/yolo/requirements.txt`
- relevant tests under `services/yolo/tests/`

## Model requirements

The core models are:

- `PredictionSession`
- `DetectionObject`

Use relationships when useful, but do not let relationships change public API response shapes.

## Hard requirements

1. Preserve existing endpoint paths, status codes, request formats, and response shapes unless the user explicitly asks for a change.
2. Do not change frontend or agent behavior.
3. Do not remove YOLO prediction functionality.
4. Do not break image upload, image saving, annotated image saving, or prediction lookup.
5. Do not use raw `sqlite3` in YOLO application code.
6. Do not use raw SQL strings for normal CRUD operations.
7. Use SQLAlchemy ORM models and session queries.
8. Keep SQLite as the default backend.
9. Support PostgreSQL through environment variables.
10. Do not commit secrets, `.env`, AWS credentials, generated databases, uploaded images, certificates, keys, coverage reports, or local cache files.
11. Add/update tests for meaningful database/API behavior affected by the requested change.
12. Do not add trivial tests just to increase coverage.
13. Do not reference missing test assets.

## Verification

Before claiming completion:

- Run the YOLO test suite.
- Run coverage if tests/coverage already exist for this service.
- Confirm no `sqlite3` or raw SQL CRUD was introduced.
- Confirm API response shapes remain compatible.
- If database backend behavior changed, verify SQLite still works.
- If PostgreSQL support changed, provide PostgreSQL verification steps or run them if Docker is available.