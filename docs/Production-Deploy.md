# FiberCRM Production Deploy

## Pre-deploy checklist
1. Set production env vars (`APP_ENV=prod`, strong `JWT_SECRET`, strict `CORS_ALLOW_ORIGINS`).
2. Confirm `SEED_DEMO_DATA=false`.
3. Ensure DB migration strategy is ready.
4. Confirm valid TLS cert/key are available for nginx.

## Deploy steps
1. Build and start:
```sh
docker compose -f docker-compose.prod.yml up -d --build
```
2. Verify health:
```sh
curl -fsS http://localhost:8000/health/live
curl -fsS http://localhost:8000/health/ready
```
3. Verify auth:
```sh
curl -fsS -X POST http://localhost:8000/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=+38000000001&password=dispatcher"
```
4. Verify realtime handshake via `/socket.io/` from frontend.

## Post-deploy smoke
1. Dispatcher loads `/dispatcher`.
2. Field Ops loads `/field`.
3. Task assignment succeeds.
4. Realtime message reaches dispatcher.
5. Photo report upload succeeds.

## Rollback
1. Revert to last known good image tag or commit.
2. Redeploy stack:
```sh
docker compose -f docker-compose.prod.yml up -d --build
```
3. Re-run health and auth checks.
