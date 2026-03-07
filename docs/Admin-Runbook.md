# FiberCRM Admin Runbook

## 1. Required environment variables
- `APP_ENV=prod`
- `APP_RELEASE=<git-sha-or-tag>`
- `DATABASE_URL=postgresql+asyncpg://...`
- `JWT_SECRET=<strong-random-secret>`
- `CORS_ALLOW_ORIGINS=https://your-frontend-domain`
- `SENTRY_DSN=<optional>`
- `SENTRY_ENVIRONMENT=prod`
- `SEED_DEMO_DATA=false`

## 2. Daily operational checks
1. `GET /health/live` returns `{"status":"live"}`.
2. `GET /health/ready` returns `{"status":"ready"}`.
3. Inspect application logs for repeated `401/429/5xx` spikes.
4. Confirm latest DB backup exists in backup storage.

## 3. JWT secret rotation
1. Generate a new secret.
2. Update secret in runtime environment.
3. Restart backend.
4. Verify `/token` login works with new tokens.
5. Notify users old sessions are invalidated.

## 4. Rate-limit monitoring
1. Track count of `429` responses for `/token`, `/users`, `/api/tasks/*/reports`.
2. If spikes are legitimate traffic, tune only specific limits, not global disable.
3. If abuse is suspected, block source IPs at edge/proxy.

## 5. Sentry incident handling
1. Open latest unhandled error in Sentry.
2. Identify release/version tag and endpoint.
3. Correlate with server logs and deploy timestamp.
4. If high severity, rollback to previous release and open hotfix issue.

## 6. Backup and restore
1. Create backup manually: `./scripts/backup_db.sh`.
2. Restore from backup: `./scripts/restore_db.sh /path/to/file.sql.gz`.
3. After restore, run app readiness check.
4. Record RTO and data validation result.

## 7. Upload storage maintenance
1. Monitor `uploads` volume growth weekly.
2. Archive or purge old uploads according to policy.
3. Validate file type and size checks stay enabled.

## 8. Emergency rollback
1. Deploy previous stable image/tag.
2. Restart backend and nginx.
3. Confirm `/health/ready` and login path.
4. Re-run smoke checks for task assignment and realtime connect.
