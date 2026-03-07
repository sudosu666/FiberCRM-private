from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_backup_scripts_exist_and_executable() -> None:
    for rel in ("scripts/backup_db.sh", "scripts/restore_db.sh", "scripts/run_e2e.sh"):
        path = ROOT / rel
        assert path.exists(), f"Missing script: {rel}"
        assert os.access(path, os.X_OK), f"Script is not executable: {rel}"


def test_production_compose_exists() -> None:
    assert (ROOT / "docker-compose.prod.yml").exists()
