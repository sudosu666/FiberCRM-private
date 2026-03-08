# FiberOps CRM

## Repository structure
- `backend/app` — FastAPI backend, domain models, routers, services
- `frontend/app` — runtime UI templates and static assets
- `frontend/prototypes` — preserved reference prototypes
- `scripts` — dev run, e2e and operational helpers
- `Plan` — architecture docs, schema, route/entity inventories

## Development (Docker Compose)
1. Ensure local shell does not override DB for containers:
- `unset DATABASE_URL`
2. Optional explicit backend DB DSN for container:
- `export BACKEND_DATABASE_URL=postgresql+asyncpg://fiber:fiberpass@db:5432/fibercrm`
3. Start stack:
- `./scripts/dev-run.sh all`
- or `docker compose up --build`
4. Optional debug/log mode:
- `./scripts/dev-run.sh all --debug --log-files`
4. Health checks:
- `http://localhost:8000/health/live`
- `http://localhost:8000/health/ready`
5. UI pages:
- `http://localhost:8000/dispatcher`
- `http://localhost:8000/designer`
- `http://localhost:8000/field`
- `http://localhost:8000/workers`
- `http://localhost:8000/warehouse`
- `http://localhost:8000/Dashboards/` (alias -> `/dispatcher`)

## Development (Local Uvicorn)
1. Copy `backend/.env.example` to `backend/.env`.
2. For local run (outside Docker) keep:
- `DATABASE_URL=postgresql+asyncpg://fiber:fiberpass@localhost:5432/fibercrm`
3. Start:
- `./scripts/dev-run.sh backend`
- debug/reload/logs: `./scripts/dev-run.sh backend --debug --log-files`
4. Verify:
- `http://localhost:8000/health/live`
- `http://localhost:8000/health/ready`
- `http://localhost:8000/dispatcher`
- `http://localhost:8000/warehouse`

## Frontend preview
- `./scripts/dev-run.sh frontend-preview`
- Opens a static preview server on `http://127.0.0.1:3000`
- Useful for layout review when backend is not needed

## Logs
- Optional runtime logs are written to `logs/`
- Typical files:
- `logs/backend.log`
- `logs/frontend-preview.log`
- `logs/compose.log`

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
