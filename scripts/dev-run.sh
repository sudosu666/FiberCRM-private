#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-}"
shift || true

DEBUG=0
LOG_FILES=0
COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

mkdir -p logs

usage() {
  cat <<'EOF'
Usage:
  scripts/dev-run.sh backend [--debug] [--log-files]
  scripts/dev-run.sh frontend-preview [--log-files]
  scripts/dev-run.sh all [--debug] [--log-files]

Options:
  --debug       enable verbose dev mode where supported
  --log-files   redirect stdout/stderr to logs/*.log

Env overrides:
  BACKEND_HOST BACKEND_PORT FRONTEND_HOST FRONTEND_PORT COMPOSE_CMD
EOF
}

while (($#)); do
  case "$1" in
    --debug) DEBUG=1 ;;
    --log-files) LOG_FILES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

run_with_logs() {
  local logfile="$1"
  shift
  if [[ "$LOG_FILES" -eq 1 ]]; then
    "$@" 2>&1 | tee "$logfile"
  else
    "$@"
  fi
}

case "$MODE" in
  backend)
    if [[ ! -x .venv/bin/python ]]; then
      echo ".venv not found. Create or restore it first." >&2
      exit 1
    fi
    UVICORN_ARGS=(backend.app.main:sio_app --host "$BACKEND_HOST" --port "$BACKEND_PORT")
    if [[ "$DEBUG" -eq 1 ]]; then
      UVICORN_ARGS+=(--reload --log-level debug)
    fi
    run_with_logs "logs/backend.log" .venv/bin/python -m uvicorn "${UVICORN_ARGS[@]}"
    ;;
  frontend-preview)
    run_with_logs "logs/frontend-preview.log" .venv/bin/python frontend/preview_server.py --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
    ;;
  all)
    COMPOSE_ARGS=(up --build)
    if [[ "$DEBUG" -eq 0 ]]; then
      COMPOSE_ARGS+=(-d)
    fi
    if [[ "$LOG_FILES" -eq 1 ]]; then
      {
        $COMPOSE_CMD "${COMPOSE_ARGS[@]}"
        $COMPOSE_CMD logs -f
      } 2>&1 | tee "logs/compose.log"
    else
      $COMPOSE_CMD "${COMPOSE_ARGS[@]}"
      if [[ "$DEBUG" -eq 1 ]]; then
        $COMPOSE_CMD logs -f
      fi
    fi
    ;;
  ""|-h|--help)
    usage
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    usage
    exit 1
    ;;
esac
