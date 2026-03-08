#!/usr/bin/env sh
set -eu

RUN_UI_TESTS="${RUN_UI_TESTS:-1}"
E2E_BASE_URL="${E2E_BASE_URL:-http://localhost:8000}"

docker compose up -d --build db backend
trap 'docker compose down -v' EXIT

for _ in $(seq 1 60); do
  if curl -fsS "${E2E_BASE_URL}/health/ready" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

E2E_BASE_URL="${E2E_BASE_URL}" pytest -q tests/e2e/api tests/e2e/realtime tests/e2e/ops
if [ "$RUN_UI_TESTS" = "1" ]; then
  E2E_BASE_URL="${E2E_BASE_URL}" pytest -q tests/e2e/ui
fi
