# FiberOps Backend

## Structure
- `app/config.py` captures environment-driven settings, security flags, and production validation.
- `app/database.py` now uses SQLModel with an async SQLAlchemy engine, keeps `init_db` + `get_session`, and creates the full schema from `Plan/fiberops_schema.sql`.
- `app/models.py` translates every table/type from the schema into SQLModel classes with UUID keys and explicit relationships.
- `app/services/realtime.py` hosts Socket.IO, JWT-gated room logic, and realtime rate limiting.
- `app/routers/` exposes `/token`, `/users`, `/api/*`, and the HTMX dispatcher route (`/dispatcher`) so the UI can hit the new backend.
- `app/main.py` wires FastAPI, Socket.IO (`sio_app`), health endpoints, optional demo seed, Sentry, and CORS middleware.

## Development
1. Copy `.env.example` to `.env` (or create your own) and point `DATABASE_URL` to your Postgres instance.
2. `pip install -r requirements.txt`.
3. Run `cd backend && uvicorn app.main:sio_app --reload` to start API + Socket.IO.
4. Verify:
- `GET /health/live`
- `GET /health/ready`

## Notes
- `SEED_DEMO_DATA` defaults to `true` in dev and must be `false` in production.
- `CORS_ALLOW_ORIGINS` must be explicit in production-like environments.
- Auth/upload/realtime limits are controlled with `RATE_LIMIT_*` settings.
