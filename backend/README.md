# FiberOps Backend (Stage 1)

Foundation for the Python + FastAPI + PostgreSQL stack that replaces the earlier NestJS plan.

## Structure
- `app/config.py` captures environment-driven secrets (Postgres URL + JWT settings) via Pydantic.
- `app/database.py` now uses SQLModel with an async SQLAlchemy engine, keeps `init_db` + `get_session`, and creates the full schema from `Plan/fiberops_schema.sql`.
- `app/models.py` translates every table/type from the schema into SQLModel classes with UUID keys and explicit relationships.
- `app/services/realtime.py` hosts the Socket.IO server, room logic for dispatchers/brigades, and a broadcast helper that other routers reuse.
- `app/routers/` exposes `/token`, `/users`, `/api/*`, and the HTMX dispatcher route (`/dispatcher`) so the UI can hit the new backend.
- `app/main.py` wires FastAPI, Socket.IO (`sio_app`), init/seed routines, and the CORS middleware.

## Development
1. Copy `.env.example` to `.env` (or create your own) and point `DATABASE_URL` to your Postgres instance.
2. `pip install -r requirements.txt` (this includes `sqlmodel` and `python-socketio[asyncio]`).
3. Run `cd backend && uvicorn backend.app.main:sio_app --reload` to start the API + Socket.IO server; tables + demo data are created at startup.

## Next
- Stage 2 (Logic Core) will continue filling the `app/services/logic.py` helpers, add GPON calculators, and expose the rest of the mission-critical endpoints.
