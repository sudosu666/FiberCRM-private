#!/usr/bin/env sh
set -eu

docker compose up -d --build db backend
trap 'docker compose down -v' EXIT

for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:8000/health/ready" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

pytest -q tests/e2e/api tests/e2e/realtime
pytest -q tests/e2e/ui
