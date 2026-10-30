#!/usr/bin/env bash
# =============================================================================
# restore_mysql.sh — Restore a MySQL database from a .sql.gz backup file
#
# Reads credentials exclusively from DATABASE_URL — no hardcoded values.
# Requires explicit confirmation before overwriting the target database.
#
# Required env var:
#   DATABASE_URL   mysql+pymysql://user:password@host:port/dbname
#
# Usage:
#   source .env && bash scripts/restore_mysql.sh backups/gnaid_db_20260511_020001.sql.gz
#
#   # Skip interactive prompt (CI / automated recovery)
#   RESTORE_CONFIRM=yes source .env && bash scripts/restore_mysql.sh <file>
# =============================================================================

set -euo pipefail

# ── 1. Argument check ────────────────────────────────────────────────────────
if [[ $# -ne 1 ]]; then
    echo "Usage: bash scripts/restore_mysql.sh <path/to/backup.sql.gz>" >&2
    exit 1
fi

BACKUP_FILE="$(realpath "$1")"

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "[restore] ERROR: File not found: ${BACKUP_FILE}" >&2
    exit 1
fi

if [[ "$BACKUP_FILE" != *.sql.gz ]]; then
    echo "[restore] ERROR: Expected a .sql.gz file, got: ${BACKUP_FILE}" >&2
    exit 1
fi

# ── 2. Resolve repo root & load .env ────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

if [[ -z "${DATABASE_URL:-}" ]]; then
    ENV_FILE="${REPO_DIR}/.env"
    if [[ -f "$ENV_FILE" ]]; then
        # shellcheck disable=SC1090
        set -a; source "$ENV_FILE"; set +a
    fi
fi

# ── 3. Validate DATABASE_URL ─────────────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "[restore] ERROR: DATABASE_URL is not set." >&2
    exit 1
fi

# ── 4. Parse DATABASE_URL ────────────────────────────────────────────────────
_url="${DATABASE_URL}"
_url="${_url#*://}"

DB_USER="${_url%%:*}"
_url="${_url#*:}"

DB_PASS="${_url%%@*}"
_url="${_url#*@}"

_hostpart="${_url%%/*}"
DB_NAME="${_url#*/}"
DB_NAME="${DB_NAME%%\?*}"

if [[ "$_hostpart" == *:* ]]; then
    DB_HOST="${_hostpart%%:*}"
    DB_PORT="${_hostpart##*:}"
else
    DB_HOST="$_hostpart"
    DB_PORT="3306"
fi

# ── 5. Sanity checks ─────────────────────────────────────────────────────────
if ! command -v mysql &>/dev/null; then
    echo "[restore] ERROR: mysql client not found in PATH." >&2
    exit 1
fi

if ! command -v gunzip &>/dev/null; then
    echo "[restore] ERROR: gunzip not found in PATH." >&2
    exit 1
fi

# Verify the file is a valid gzip archive before doing anything destructive
if ! gunzip --test "$BACKUP_FILE" 2>/dev/null; then
    echo "[restore] ERROR: File is not a valid gzip archive: ${BACKUP_FILE}" >&2
    exit 1
fi

FILE_SIZE="$(du -sh "$BACKUP_FILE" | cut -f1)"
FILE_NAME="$(basename "$BACKUP_FILE")"

# ── 6. Safety confirmation ───────────────────────────────────────────────────
echo ""
echo "┌──────────────────────────────────────────────────────────┐"
echo "│                  ⚠  DATABASE RESTORE  ⚠                  │"
echo "├──────────────────────────────────────────────────────────┤"
printf "│  Target database : %-38s │\n" "${DB_NAME}"
printf "│  Host            : %-38s │\n" "${DB_HOST}:${DB_PORT}"
printf "│  Restore user    : %-38s │\n" "${DB_USER}"
printf "│  Backup file     : %-38s │\n" "${FILE_NAME}"
printf "│  Backup size     : %-38s │\n" "${FILE_SIZE}"
echo "├──────────────────────────────────────────────────────────┤"
echo "│  ALL EXISTING DATA IN '${DB_NAME}' WILL BE OVERWRITTEN.  │"
echo "└──────────────────────────────────────────────────────────┘"
echo ""

# Allow non-interactive override via env var (e.g. CI pipelines)
if [[ "${RESTORE_CONFIRM:-}" != "yes" ]]; then
    read -r -p "Type the database name to confirm restore: " CONFIRM_INPUT
    if [[ "$CONFIRM_INPUT" != "$DB_NAME" ]]; then
        echo "[restore] Aborted — input did not match database name '${DB_NAME}'."
        exit 1
    fi
fi

# ── 7. Restore ───────────────────────────────────────────────────────────────
echo "[restore] Starting restore from: ${BACKUP_FILE}"
START_TIME="$(date +%s)"

export MYSQL_PWD="$DB_PASS"

gunzip --stdout "$BACKUP_FILE" | mysql \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --user="$DB_USER" \
    --database="$DB_NAME"

unset MYSQL_PWD

END_TIME="$(date +%s)"
ELAPSED=$(( END_TIME - START_TIME ))

echo "[restore] Restore complete in ${ELAPSED}s."
echo "[restore] Database '${DB_NAME}' on ${DB_HOST}:${DB_PORT} has been restored."
