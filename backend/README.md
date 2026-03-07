# FiberOps Backend (Stage 1)

Foundation for the Python + FastAPI + PostgreSQL stack that replaces the previous NestJS plan.

## Structure
- `app/config.py` picks up the `DATABASE_URL` and JWT settings via Pydantic.
- `app/database.py` exposes an `AsyncSessionLocal` sessionmaker and declarative base.
- `app/models.py` mirrors the `Plan/Tables` definitions: roles, tenders, buildings, muffles, fibers, brigades, tasks, and a lightweight user table.
- `app/auth.py` centralizes password hashing and token creation/validation.
- `app/routers` implements `/token` and `/users` endpoints plus auth helpers for requiring roles in later stages.

## Development
1. Copy `.env.example` to `.env` and point it to a running Postgres instance.
2. `pip install -r requirements.txt`.
3. Run `uvicorn app.main:app --reload` to start the API; it will create the schema on startup.

## Next
- Stage 2 (Logic Core) will wire the task/tender state machine, implement brigade assignments, and expose endpoints consumed by each of the new HTML views.
