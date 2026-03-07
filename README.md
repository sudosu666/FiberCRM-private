# FiberOps CRM

## Development run
1. Copy `backend/.env.example` to `backend/.env`.
2. Start stack: `docker compose up --build`.
3. Health checks:
- `http://localhost:8000/health/live`
- `http://localhost:8000/health/ready`

## Production run
1. Copy `.env.prod.example` to `.env` and set real secrets.
2. Start production profile: `docker compose -f docker-compose.prod.yml up -d --build`.
3. Review [docs/Production-Deploy.md](/home/linux/Documents/FiberCRM/docs/Production-Deploy.md) and [docs/Admin-Runbook.md](/home/linux/Documents/FiberCRM/docs/Admin-Runbook.md).

## Security and monitoring additions (Stage 9)
- Environment-based CORS and secret validation.
- HTTP and Socket.IO rate limiting.
- Sentry integration hook.
- DB backup automation scripts and backup service in production compose.
- E2E smoke tests in CI (`tests/e2e/api`, `tests/e2e/realtime`).
