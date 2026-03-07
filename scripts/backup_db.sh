#!/usr/bin/env sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${BACKUP_DIR}/fibercrm_${STAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"
pg_dump --no-owner --no-privileges | gzip -9 > "${OUT_FILE}"

find "${BACKUP_DIR}" -type f -name "fibercrm_*.sql.gz" -mtime +"${RETENTION_DAYS}" -delete
echo "Backup created: ${OUT_FILE}"
