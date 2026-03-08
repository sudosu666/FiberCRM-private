# FiberOps CRM

## Development (Docker Compose)
1. Ensure local shell does not override DB for containers:
- `unset DATABASE_URL`
2. Optional explicit backend DB DSN for container:
- `export BACKEND_DATABASE_URL=postgresql+asyncpg://fiber:fiberpass@db:5432/fibercrm`
3. Start stack:
- `docker compose up --build`
4. Health checks:
- `http://localhost:8000/health/live`
- `http://localhost:8000/health/ready`
5. UI pages:
- `http://localhost:8000/dispatcher`
- `http://localhost:8000/field`
- `http://localhost:8000/workers`
- `http://localhost:8000/warehouse`
- `http://localhost:8000/Dashboards/` (alias -> `/dispatcher`)

## Development (Local Uvicorn)
1. Copy `backend/.env.example` to `backend/.env`.
2. For local run (outside Docker) keep:
- `DATABASE_URL=postgresql+asyncpg://fiber:fiberpass@localhost:5432/fibercrm`
3. Start:
- `cd backend && uvicorn app.main:sio_app --reload`
4. Verify:
- `http://localhost:8000/health/live`
- `http://localhost:8000/health/ready`
- `http://localhost:8000/dispatcher`
- `http://localhost:8000/warehouse`

## Production run
1. Fill real secrets in `.env.prod`.
2. Start production profile: `docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build`.
3. Review [docs/Production-Deploy.md](/home/linux/Documents/FiberCRM/docs/Production-Deploy.md) and [docs/Admin-Runbook.md](/home/linux/Documents/FiberCRM/docs/Admin-Runbook.md).

## Security and monitoring additions (Stage 9)
- Environment-based CORS and secret validation.
- HTTP and Socket.IO rate limiting.
- Sentry integration hook.
- DB backup automation scripts and backup service in production compose.
- E2E smoke tests in CI (`tests/e2e/api`, `tests/e2e/realtime`).

## Backend notes
- Main entrypoint: `backend/app/main.py` (`sio_app`).
- Backend env template: `backend/.env.example`.
- Never use `DATABASE_URL=...localhost...` for Docker backend container.
- Use `BACKEND_DATABASE_URL=postgresql+asyncpg://fiber:fiberpass@db:5432/fibercrm` for Docker Compose backend service.
- `SEED_DEMO_DATA=true` only for local dev, set `false` for production-like environments.
