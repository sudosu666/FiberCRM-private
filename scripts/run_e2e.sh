#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_UI_TESTS="${RUN_UI_TESTS:-1}"
E2E_BASE_URL="${E2E_BASE_URL:-http://127.0.0.1:8000}"
COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"

if [[ "$COMPOSE_CMD" = "docker compose" ]]; then
  if command -v docker >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
  else
    echo "[run_e2e] neither docker nor docker-compose is available in PATH" >&2
    exit 1
  fi
fi

echo "[run_e2e] Starting test stack (db, redis, backend)"
$COMPOSE_CMD up -d --build db redis backend
trap '$COMPOSE_CMD down -v' EXIT

echo "[run_e2e] Waiting for backend readiness inside container at ${E2E_BASE_URL}/health/ready"
for _ in $(seq 1 90); do
  if $COMPOSE_CMD exec -T backend python - <<'PY' >/dev/null 2>&1
import urllib.request
urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=3)
PY
  then
    break
  fi
  sleep 2
done

if ! $COMPOSE_CMD exec -T backend python - <<'PY' >/dev/null 2>&1
import urllib.request
urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=3)
PY
then
  echo "[run_e2e] backend did not become ready in time" >&2
  exit 1
fi

echo "[run_e2e] Running API/Realtime/Ops e2e tests in backend container"
$COMPOSE_CMD exec -T backend env E2E_BASE_URL="${E2E_BASE_URL}" python -m pytest -q tests/e2e/api tests/e2e/realtime tests/e2e/ops

if [[ "$RUN_UI_TESTS" = "1" ]]; then
  echo "[run_e2e] Ensuring Playwright browser is installed in backend container"
  $COMPOSE_CMD exec -T backend python -m playwright install --with-deps chromium
  echo "[run_e2e] Running UI Playwright e2e tests in backend container"
  $COMPOSE_CMD exec -T backend env E2E_BASE_URL="${E2E_BASE_URL}" python -m pytest -q tests/e2e/ui
fi

echo "[run_e2e] All selected e2e test suites passed"
