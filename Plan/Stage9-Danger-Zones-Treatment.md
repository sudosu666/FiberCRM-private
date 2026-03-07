# Stage 9 - Dangerous Zones Treatment (Step by Step)

## Scope
This runbook is the direct treatment plan for the critical/high-risk zones found in the Stage 9 review.

## Zone 1 - Auth router import defect (service boot risk)
Risk:
- `backend/app/routers/auth_router.py` imports `get_session` from `.database`, but the module is in `backend/app/database.py`.

Treatment steps:
1. Change import in `auth_router.py` to `from ..database import get_session`.
2. Run `python -m compileall backend/app`.
3. Run a startup smoke: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
4. Call `GET /` and `POST /token` with invalid credentials to ensure router is mounted.

Done criteria:
- Backend starts without import error.
- `/token` endpoint responds (401 for bad credentials is expected).

## Zone 2 - Pydantic settings incompatibility (runtime config break)
Risk:
- Code uses `BaseSettings` from `pydantic`, but project pins Pydantic v2.

Treatment steps:
1. Add `pydantic-settings` to `backend/requirements.txt`.
2. Replace settings class with `from pydantic_settings import BaseSettings, SettingsConfigDict`.
3. Define explicit env mapping and defaults only for dev.
4. Add validation for required production vars (`JWT_SECRET`, DB URL, CORS list).
5. Add `APP_ENV` switch (`dev`, `staging`, `prod`).
6. Re-run `python -m compileall backend/app`.
7. Boot once with dev env and once with prod env to verify behavior.

Done criteria:
- Settings load cleanly under Pydantic v2.
- Production boot fails fast when required secrets are missing.

## Zone 3 - Socket.IO auth bypass (data exposure risk)
Risk:
- Client can self-claim dispatcher role and join privileged room.

Treatment steps:
1. In `services/realtime.py`, require JWT for `connect`.
2. Decode token and reject connection on decode failure.
3. Derive role only from token payload, never from raw `auth.role`.
4. Validate brigade room membership from token identity and DB relation.
5. Disconnect unauthorized client immediately.
6. Add event-level authorization checks for `chat_message` and `progress_update`.
7. Add negative tests for forged role and missing token.

Done criteria:
- Unauthenticated client cannot join dispatcher room.
- Forged role in payload has no effect.

## Zone 4 - Permissive CORS (cross-origin abuse risk)
Risk:
- `allow_origins=["*"]` in production.

Treatment steps:
1. Add `CORS_ALLOW_ORIGINS` env variable as explicit comma-separated list.
2. Keep wildcard only in local dev mode.
3. Configure credentials policy explicitly (`allow_credentials=True` only where needed).
4. Validate preflight behavior from allowed and disallowed origins.

Done criteria:
- Only trusted frontends pass CORS in production profile.

## Zone 5 - Hardcoded secrets (credential leakage risk)
Risk:
- Default DB credentials and JWT secret are hardcoded in code/compose.

Treatment steps:
1. Remove hardcoded production secrets from `config.py` and `docker-compose.yml`.
2. Keep `.env.example` placeholders only.
3. Add startup check that blocks known weak defaults in non-dev env.
4. Rotate credentials and JWT secret before production deploy.
5. Update CI/CD to inject secrets from platform secret manager.

Done criteria:
- No real secrets in repository-tracked files.
- Deployment relies on environment-provided secrets only.

## Zone 6 - SQL echo enabled (sensitive logs risk)
Risk:
- SQL statements and parameter values may leak to logs.

Treatment steps:
1. Add `SQL_ECHO` flag in settings, default `False`.
2. Use `create_async_engine(..., echo=settings.sql_echo)`.
3. Force `False` in production env.
4. Verify logs under load do not expose SQL bind data.

Done criteria:
- Production logs exclude SQL statement dumps.

## Zone 7 - Dev runtime in production (`--reload`)
Risk:
- Development reloader is not production-safe and increases instability.

Treatment steps:
1. Replace dev command with production process model (Gunicorn + Uvicorn workers or equivalent).
2. Add separate compose/profile for prod vs dev.
3. Configure worker count, timeout, graceful shutdown.
4. Add readiness check gating traffic until app is ready.

Done criteria:
- Production runtime uses stable multi-worker serving mode.

## Zone 8 - Unbounded file upload path (DoS/malware/storage risk)
Risk:
- Base64 uploads have no size/content controls.

Treatment steps:
1. Add max payload size (request + decoded bytes).
2. Validate MIME type and extension whitelist (`.jpg`, `.jpeg`, `.png`, `.webp`).
3. Reject dangerous filenames; always use server-generated random name.
4. Optionally run malware scanning hook before persistence.
5. Move artifacts to object storage or isolated upload volume with retention policy.
6. Add upload rate limits per user/IP.

Done criteria:
- Oversized and invalid files are rejected with safe errors.
- Upload storage growth is controlled.

## Zone 9 - Startup demo seeding in production (data integrity risk)
Risk:
- Boot path always executes demo seed flow.

Treatment steps:
1. Gate seeding behind `SEED_DEMO_DATA=false` default.
2. Run seed only in local/dev environments.
3. Add idempotency guard if seed remains callable manually.

Done criteria:
- Production boot never mutates business data via demo seed.

## Zone 10 - Missing health/readiness and weak CI gates
Risk:
- No DB readiness endpoint and CI does not test runtime behavior.

Treatment steps:
1. Add `/health/live` (process up) and `/health/ready` (DB reachable).
2. Extend CI with:
- import tests
- app startup tests
- auth path tests
- rate limit tests
3. Add migration check in CI and deploy pipeline.
4. Add smoke step after deploy (`/health/ready`, `/token`, realtime connect).

Done criteria:
- CI fails on boot/auth regressions.
- Deploy gates on readiness and smoke checks.

## Execution order
1. Boot blockers: Zone 1 + Zone 2.
2. Access control: Zone 3 + Zone 4 + Zone 5.
3. Runtime hardening: Zone 6 + Zone 7 + Zone 8.
4. Operational safety: Zone 9 + Zone 10.

