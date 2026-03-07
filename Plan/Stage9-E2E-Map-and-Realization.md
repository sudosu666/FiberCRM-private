# Stage 9 - E2E Map and Realization

## Objective
Create reliable end-to-end confidence across API, realtime, UI, and production operations for FiberCRM.

## E2E map

### Track A - API E2E (FastAPI HTTP)
Coverage:
- Auth: `/token`, `/users`
- Core ops: `/api/tasks`, `/api/tasks/{id}/assign`
- Reporting: `/api/tasks/{id}/reports`
- Analytics: `/api/field/metrics`
- Health: `/health/live`, `/health/ready`

Primary flows:
1. Login -> read tasks -> assign task -> verify task status changed.
2. Builder report upload -> dispatcher metrics update.
3. Negative auth paths (invalid/expired token).
4. Rate-limited paths return `429`.

### Track B - Realtime E2E (Socket.IO)
Coverage:
- `connect` authorization
- `chat_message`
- `progress_update`
- room routing: `dispatchers`, `brigade_{id}`

Primary flows:
1. Authorized dispatcher receives brigade events.
2. Brigade sends chat/progress and sees own room echo.
3. Unauthorized or forged role client is rejected.
4. Event flood triggers rate limit behavior.

### Track C - UI E2E (Dispatcher + Field Ops pages)
Coverage:
- Dispatcher page load and data render.
- Field Ops task lifecycle (task selection, step progression, photo report, chat).
- Realtime updates reflected in UI widgets.

Primary flows:
1. Dispatcher assigns a task and sees board refresh.
2. Field Ops submits progress; dispatcher notification rail updates.
3. Field Ops submits photo; dispatcher sees new photo event.

### Track D - Ops E2E (Backup/restore/deploy)
Coverage:
- Scheduled backup generation and retention.
- Restore drill into clean database.
- Production startup smoke and readiness.
- Rollback validation.

Primary flows:
1. Backup job writes artifact to target storage.
2. Restore latest backup and boot app successfully.
3. Deploy new release, run smoke, rollback if smoke fails.

## Realization architecture

### Test environments
1. `local-dev`: developer machine, quick smoke.
2. `ci-e2e`: ephemeral stack via Docker Compose.
3. `preprod`: production-like config with real ingress rules.

### Data strategy
- Seed deterministic fixtures: dispatcher, brigade, tasks, steps, buildings.
- Use isolated DB per pipeline run.
- Generate unique IDs per test run to avoid collisions.

### Tooling recommendation
- API and realtime: `pytest`, `httpx`, `python-socketio` client.
- UI browser E2E: `playwright`.
- Orchestration: Docker Compose test profile.
- Reporting: JUnit XML + HTML artifact + screenshot/video on UI failures.

## Implementation phases

### Phase 1 - Foundation
1. Add `tests/e2e/` structure.
2. Add Compose profile for e2e (`db`, `backend`, `nginx` optional).
3. Add fixture loader endpoint or migration seed for deterministic data.
4. Add CI job `e2e-smoke` triggered on PR.

Exit gate:
- One happy-path API flow passes in CI.

### Phase 2 - Security-critical E2E
1. Add auth negative tests and token-expiry tests.
2. Add Socket.IO unauthorized access tests.
3. Add rate limit tests for `/token`, `/users`, `/reports`.
4. Add upload boundary tests (size/type/base64).

Exit gate:
- Security-negative suite passes and blocks merge on failure.

### Phase 3 - Business workflow E2E
1. Add task assignment lifecycle tests.
2. Add progress + chat persistence tests.
3. Add photo report -> dispatcher metrics propagation tests.
4. Add cross-role visibility and room isolation tests.

Exit gate:
- Main dispatcher/field workflow passes end-to-end.

### Phase 4 - UI E2E
1. Add Playwright smoke for dispatcher and field pages.
2. Add interaction scenarios for assign/progress/photo/chat.
3. Add visual evidence capture for failed assertions.

Exit gate:
- UI critical journeys pass on every PR.

### Phase 5 - Ops E2E
1. Add backup job execution test.
2. Add restore drill test in isolated DB.
3. Add post-deploy smoke script and rollback rehearsal.
4. Add scheduled nightly full e2e run.

Exit gate:
- Backup+restore and deploy smoke are automated and green.

## Suggested repository layout
```text
tests/
  e2e/
    api/
      test_auth_flow.py
      test_task_lifecycle.py
      test_upload_limits.py
    realtime/
      test_socket_auth.py
      test_chat_progress_flow.py
    ui/
      dispatcher.spec.ts
      field_ops.spec.ts
    ops/
      test_backup_restore.py
      test_deploy_smoke.py
  fixtures/
    seed_e2e.sql
scripts/
  run_e2e.sh
  backup_db.sh
  restore_db.sh
```

## CI/CD integration map
1. PR pipeline:
- lint + unit + e2e-smoke (API + auth + one realtime check).
2. Main branch pipeline:
- full e2e (API + realtime + UI).
3. Nightly:
- full e2e + backup/restore drill.
4. Pre-deploy:
- migration check + readiness smoke.
5. Post-deploy:
- production smoke + rollback guard.

## Quality gates
- No production release if any security e2e test fails.
- No release if restore drill has not passed within the last 24 hours.
- No release if readiness endpoint fails or Socket.IO auth check fails.

## First sprint execution checklist
1. Implement health endpoints and auth/socket fixes first.
2. Stand up `tests/e2e/api` and `tests/e2e/realtime` with 6-10 critical cases.
3. Wire `e2e-smoke` into CI as required status check.
4. Add Playwright smoke for dispatcher + field pages.
5. Add backup/restore scripted drill and nightly job.

