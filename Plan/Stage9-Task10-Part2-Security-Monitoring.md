# Stage 9 Plan — Task 10 (Part 2)

## Goal
Deliver the missing production-readiness slice for FiberCRM:
- rate limiting
- Sentry error tracking
- automatic PostgreSQL backups
- administrator documentation
- final production deploy flow

## Current baseline
- Latest visible product work stops at Stage 7 (`c2ce599`, 2026-03-07).
- The backend is still configured as a development stack, not a production system.
- There is no rate limiter, no Sentry integration, no backup automation, no admin runbook, and no production deployment manifest.

## Implementation plan

### 1. Configuration hardening
- Replace hardcoded defaults in `backend/app/config.py` with explicit environment variables and fail-fast validation for production secrets.
- Split development defaults from production settings.
- Add environment flags for `APP_ENV`, `SENTRY_DSN`, `RATE_LIMIT_ENABLED`, `BACKUP_S3_BUCKET`, `BACKUP_RETENTION_DAYS`, and trusted CORS origins.
- Stop SQL query logging by default in production.

### 2. HTTP and Socket.IO rate limiting
- Add request limits for `/token`, `/users`, report upload endpoints, and Socket.IO event handlers.
- Apply stricter limits to auth and upload paths, broader limits to read APIs.
- Key by IP for anonymous traffic and by user ID / phone for authenticated traffic.
- Return `429` with structured error payloads and `Retry-After` headers.
- Add server-side guards for payload size on base64 photo uploads and chat flooding.

### 3. Sentry and observability
- Initialize Sentry in app startup with environment, release, sample-rate, and PII controls.
- Capture FastAPI exceptions, background task failures, and startup errors.
- Add request correlation IDs to logs.
- Expose `/health/live` and `/health/ready` endpoints for deployment health checks.
- Add basic structured logging so production incidents are traceable without SQL echo noise.

### 4. Database backup automation
- Add a backup container or scheduled job that runs `pg_dump` against Postgres.
- Compress dumps, encrypt if required by environment, and ship to object storage.
- Add retention policy, restore verification, and alerting on failed backup jobs.
- Document RPO/RTO targets and a restore drill.

### 5. Production deployment
- Replace the current dev `uvicorn --reload` compose flow with a production service definition.
- Use a production ASGI process model and separate runtime config from local `.env.example`.
- Replace self-signed local TLS assumptions with externally managed certificates or production ingress.
- Add persistent volume handling for uploaded report assets or move uploads to object storage.
- Add a deploy checklist covering migrations, smoke checks, rollback, and post-deploy verification.

### 6. Administrator documentation
- Create an admin runbook covering:
- environment variables
- first deploy
- rotating JWT secrets
- reading Sentry alerts
- checking rate-limit violations
- backup restore procedure
- handling disk pressure from uploads
- incident response and rollback

## Recommended delivery order
1. Fix boot/runtime correctness issues blocking trustworthy deployment.
2. Harden config and add health endpoints.
3. Add rate limiting for auth, uploads, and Socket.IO.
4. Add Sentry and structured logging.
5. Add backup automation and restore test.
6. Write admin docs.
7. Perform production deploy and smoke verification.

## Exit criteria
- Production boot works from clean environment variables only.
- Auth and upload abuse paths return `429`.
- Unhandled exceptions appear in Sentry with release/environment tags.
- Scheduled backups execute automatically and at least one restore drill succeeds.
- Admin runbook exists and matches the actual deployment steps.
- Production deployment is reproducible and smoke-tested.
