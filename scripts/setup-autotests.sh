#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[setup-autotests] Project root: $ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[error] python3 is not installed"
  exit 1
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
  echo "[error] python3-venv is missing."
  echo "Install it (Ubuntu/Debian): sudo apt install python3-venv"
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "[setup] Creating .venv"
  python3 -m venv .venv
fi

if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  echo "[setup] pip is missing in .venv, bootstrapping with get-pip.py"
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
  .venv/bin/python /tmp/get-pip.py
fi

echo "[setup] Upgrading pip tooling"
.venv/bin/python -m pip install --upgrade pip setuptools wheel

echo "[setup] Installing backend + test dependencies"
.venv/bin/pip install -r backend/requirements.txt

echo "[setup] Installing Playwright browser (Chromium)"
.venv/bin/python -m playwright install chromium

echo "[done] Autotest environment is ready."
echo "Run UI tests:"
echo "  E2E_BASE_URL=http://localhost:8000 .venv/bin/python -m pytest -q tests/e2e/ui"
