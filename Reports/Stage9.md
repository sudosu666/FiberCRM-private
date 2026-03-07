# Stage 9 Report — Security, Monitoring, and Production Readiness Review

## Scope
- Review the git history and current codebase state after Stage 7.
- Assess readiness for Stage 9 Task 10 (Part 2): security, monitoring, backups, admin documentation, and production deployment.
- Provide a strict gap analysis plus an expanded test matrix.

## Git history review
- The visible staged delivery path is: Stage 1 foundation, Stage 2 logic core, Stage 3 DevOps baseline, Stage 5 realtime dispatcher, Stage 6 Field Ops PWA, and Stage 7 dispatcher analytics.
- The newest local commit is `c2ce599` dated `2026-03-07` with message `Stage 7: Dispatcher analytics`.
- There is no Stage 8 or Stage 9 implementation commit yet, so the requested security/monitoring work is still outstanding.
- The history shows feature growth, but not a corresponding production-hardening pass.

## Code review findings

### Critical
- `backend/app/routers/auth_router.py:13` imports `get_session` from `.` `database`, but the routers package has no `database.py`. This breaks the auth router import path and would stop the service from booting once that module is loaded.
- `backend/app/config.py:1` uses `BaseSettings` from `pydantic`, while `backend/requirements.txt:8` pins `pydantic==2.7.0`. In Pydantic v2, `BaseSettings` moved out of `pydantic`, so the declared dependency set is incompatible with the current config module.
- `backend/app/services/realtime.py:80` accepts Socket.IO connections without enforcing a valid token. Any client can self-assign `role=Dispatcher` and join the dispatcher room at `backend/app/services/realtime.py:95-98`, which exposes internal live operations data.

### High
- `backend/app/main.py:16-21` enables fully permissive CORS (`*` origins, methods, headers). That is acceptable for early dev, but not for a production CRM handling auth tokens and operational data.
- `backend/app/config.py:5-6` and `docker-compose.yml:28-30` hardcode database credentials and JWT secrets. This creates immediate secret leakage and environment drift risk.
- `backend/app/database.py:9` enables SQLAlchemy `echo=True`, which will leak SQL statements and potentially sensitive parameters into production logs.
- `docker-compose.yml:33` runs `uvicorn` with `--reload`, which is a development-only mode and not suitable for final production deploys.
- `backend/app/routers/logic_router.py:31-46` accepts unbounded base64 photo payloads and writes files directly under the app static tree. There is no content-type validation, payload size cap, malware scan hook, or storage lifecycle management.

### Medium
- `backend/app/main.py:30-34` seeds demo data on every startup. Even if the seed helper is idempotent, production startup should not depend on demo seeding side effects.
- `backend/app/main.py:36-42` exposes only trivial root endpoints; there is no readiness endpoint for DB dependency checks, and no observability-oriented health surface.
- `.github/workflows/ci.yml:36-39` only runs `compileall` and `docker compose config`. CI does not exercise imports, startup, auth flows, rate limiting, or backup/restore behavior.
- `nginx/nginx.conf:1-18` is still a local self-signed reverse proxy config. It does not document production TLS handling, websocket proxy tuning, security headers, or upstream timeouts.

## Stage 9 status
- `Rate limiting`: missing
- `Sentry`: missing
- `Automatic DB backups`: missing
- `Administrator documentation`: missing
- `Final production deploy flow`: missing

## Recommended Stage 9 work
- Fix the boot/runtime defects first, especially the broken import path and Pydantic settings incompatibility.
- Lock down authentication boundaries for HTTP and Socket.IO before adding external exposure.
- Add targeted rate limits to login, registration, chat, progress, and photo upload paths.
- Add Sentry plus structured logs and explicit liveness/readiness endpoints.
- Add automated PostgreSQL dumps with retention and restore verification.
- Replace the development compose/runtime path with a documented production deploy process.

## Large test scenario matrix

### A. Boot and configuration
- Start backend with complete production env vars.
- Start backend with missing `JWT_SECRET` and verify fail-fast behavior.
- Start backend with invalid `DATABASE_URL`.
- Start backend with malformed `SENTRY_DSN`.
- Start backend with empty trusted origins list.
- Start backend with SQL logging disabled.
- Start backend with SQL logging enabled in development only.
- Start backend twice and verify startup remains idempotent.

### B. Authentication and authorization
- Login with valid dispatcher credentials.
- Login with valid builder credentials.
- Login with wrong password.
- Login with unknown phone.
- Repeated failed login attempts from one IP until rate limit is hit.
- Repeated failed login attempts across multiple usernames from one IP.
- Registration with a duplicate phone number.
- Registration with invalid payload shape.
- Access authenticated endpoint with missing bearer token.
- Access authenticated endpoint with expired token.
- Access authenticated endpoint with forged token signature.
- Access dispatcher-only route as non-dispatcher.
- Rotate JWT secret and verify old tokens are rejected.

### C. Socket.IO security
- Connect to Socket.IO with a valid dispatcher token.
- Connect to Socket.IO with a valid brigade token.
- Connect without token and verify room join is denied.
- Connect with forged dispatcher role in auth payload and verify denial.
- Send chat event for a task outside caller scope.
- Send progress event for a task outside caller scope.
- Flood chat events until the rate limiter returns rejection.
- Flood progress events until the rate limiter returns rejection.
- Connect many clients concurrently and verify room isolation.

### D. Rate limiting behavior
- Hit `/token` below threshold and verify success.
- Hit `/token` above threshold and verify `429`.
- Verify `Retry-After` header is present on auth throttling.
- Hit `/users` registration above threshold.
- Hit `/api/tasks/{id}/reports` above upload threshold.
- Hit read-only endpoints and confirm higher, safe thresholds.
- Verify counters reset after cooldown.
- Verify rate limits are scoped correctly per IP.
- Verify authenticated rate limits are scoped correctly per user.
- Verify reverse proxy forwards client IP correctly.

### E. Upload and storage security
- Upload a valid PNG photo report.
- Upload a valid JPEG photo report.
- Upload invalid base64.
- Upload empty payload.
- Upload oversized payload and verify rejection.
- Upload executable content with image extension and verify rejection.
- Upload filename with path traversal characters.
- Upload unsupported extension.
- Upload duplicate filenames and verify server-side randomization prevents collision.
- Verify uploaded files are not executable by the web server.
- Verify upload metadata is stored correctly in DB.

### F. API and data integrity
- Assign task to an existing brigade.
- Assign task to a nonexistent brigade.
- Create report for an existing task.
- Create report for a nonexistent task.
- Trigger progress update and verify next task step changes once.
- Trigger duplicate progress update and verify idempotent handling or expected sequential progression.
- Confirm tender/building aggregate state refreshes after assignment.
- Confirm notifications are created for dispatcher on progress update.
- Confirm chat persistence stores sender, body, and timestamp correctly.

### G. Observability and Sentry
- Trigger unhandled exception in HTTP route and verify Sentry event creation.
- Trigger unhandled exception during startup and verify capture path.
- Trigger exception in Socket.IO handler and verify capture path.
- Verify PII scrubbing settings for auth payloads.
- Verify Sentry tags include environment and release version.
- Verify logs include request correlation IDs.
- Verify logs omit raw secrets and bearer tokens.
- Verify noisy 4xx auth failures are sampled/filtered as intended.

### H. Backups and restore
- Run scheduled backup job manually.
- Verify backup artifact is created with timestamped name.
- Verify backup artifact is compressed.
- Verify backup artifact reaches remote storage.
- Verify retention policy deletes expired backups.
- Simulate backup destination outage and verify alerting.
- Restore latest backup into clean database.
- Restore older backup into clean database.
- Validate restored row counts against source.
- Validate application boot against restored database.
- Document measured restore duration versus target RTO.

### I. Production deploy
- Build production image from clean checkout.
- Run DB migrations before deploy.
- Deploy backend without `--reload`.
- Verify websocket connectivity through production proxy.
- Verify TLS termination and redirect behavior.
- Verify security headers on proxied responses.
- Verify health checks gate traffic before app readiness.
- Perform rolling deploy with no data loss.
- Perform rollback to prior image tag.
- Verify uploaded assets remain available after deploy.

### J. Admin operations
- Follow runbook for first deployment on a new host.
- Follow runbook for JWT secret rotation.
- Follow runbook for restoring from backup.
- Follow runbook for handling a Sentry alert.
- Follow runbook for investigating rate-limit spikes.
- Follow runbook for disk usage cleanup due to uploads.
- Follow runbook for rotating DB credentials.
- Follow runbook for emergency rollback after failed deploy.

## Conclusion
- The project is functionally ahead of its operational maturity.
- Before a final production deploy, the repo needs a dedicated hardening pass, because current auth, config, runtime, and observability choices still reflect a development environment rather than a protected production CRM.
