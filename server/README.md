# FastAPI Project Configuration

## Directory Structure & Purpose

- `app/`: Main source code package.
  - `main.py`: Application entry point.
  - `core/`: Global configuration, security (JWT), and logging.
  - `db/`: Database session management and migrations (Alembic).
  - `models/`: SQLAlchemy ORM models (database tables).
  - `schemas/`: Pydantic models for request/response validation.
  - `api/`: API routing and versioning.
    - `deps/`: Shared dependencies (e.g., `get_db`).
    - `v1/`: Version 1 endpoints.
  - `services/`: Business logic layer.
  - `repositories/`: Data access layer (CRUD operations).
  - `utils/`: Common helper functions.
  - `exceptions/`: Custom exceptions and global handlers.
  - `middlewares/`: Custom application middlewares.
  - `tests/`: Unit and integration tests.

## Environment Setup
- Conda Environment: `demo_core`
- Database: PostgreSQL
