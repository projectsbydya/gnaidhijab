#!/usr/bin/env bash
# =============================================================================
# backup_mysql.sh — Daily compressed MySQL backup with 7-day retention
#
# Reads credentials exclusively from environment variables.
# Designed to be called by cron or any CI/CD scheduler.
#
# Required env vars (set in .env or export before running):
#   DATABASE_URL   mysql+pymysql://user:password@host:port/dbname
#                  (port is optional — defaults to 3306)
#
# Optional env vars:
#   BACKUP_DIR     Directory to store backups  (default: <repo_root>/backups)
#   BACKUP_RETAIN  Number of most-recent backups to keep  (default: 7)
#
# Usage:
#   # One-off
#   source .env && bash scripts/backup_mysql.sh
#
#   # Cron — daily at 02:00
#   0 2 * * * cd /var/www/gnaid && source .env && bash scripts/backup_mysql.sh >> /var/log/gnaid_backup.log 2>&1
# =============================================================================

set -euo pipefail

# ── 1. Resolve script & repo directories ────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# ── 2. Load .env if DATABASE_URL not already in environment ─────────────────
if [[ -z "${DATABASE_URL:-}" ]]; then
    ENV_FILE="${REPO_DIR}/.env"
    if [[ -f "$ENV_FILE" ]]; then
        # shellcheck disable=SC1090
        set -a; source "$ENV_FILE"; set +a
    fi
fi

# ── 3. Validate DATABASE_URL ─────────────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "[backup] ERROR: DATABASE_URL is not set." >&2
    exit 1
fi

# ── 4. Parse DATABASE_URL ────────────────────────────────────────────────────
# Format: mysql+pymysql://user:password@host:port/dbname
#         scheme+driver  user  pass      host port  db
_url="${DATABASE_URL}"
_url="${_url#*://}"          # strip scheme

DB_USER="${_url%%:*}"        # everything before first ':'
_url="${_url#*:}"            # strip user:

DB_PASS="${_url%%@*}"        # everything before '@'
_url="${_url#*@}"            # strip pass@

_hostpart="${_url%%/*}"      # host:port or host
DB_NAME="${_url#*/}"         # everything after first '/'
DB_NAME="${DB_NAME%%\?*}"    # strip query string if any

if [[ "$_hostpart" == *:* ]]; then
    DB_HOST="${_hostpart%%:*}"
    DB_PORT="${_hostpart##*:}"
else
    DB_HOST="$_hostpart"
    DB_PORT="3306"
fi

# ── 5. Config ────────────────────────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-${REPO_DIR}/backups}"
BACKUP_RETAIN="${BACKUP_RETAIN:-7}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
FILENAME="${DB_NAME}_${TIMESTAMP}.sql.gz"
FILEPATH="${BACKUP_DIR}/${FILENAME}"

mkdir -p "$BACKUP_DIR"

# ── 6. Sanity checks ─────────────────────────────────────────────────────────
if ! command -v mysqldump &>/dev/null; then
    echo "[backup] ERROR: mysqldump not found in PATH." >&2
    exit 1
fi
if ! command -v gzip &>/dev/null; then
    echo "[backup] ERROR: gzip not found in PATH." >&2
    exit 1
fi

echo "[backup] Starting backup: ${DB_NAME} → ${FILEPATH}"

# ── 7. Dump & compress ───────────────────────────────────────────────────────
# MYSQL_PWD avoids the "password on command line" warning without a credentials file.
MYSQL_PWD="$DB_PASS" mysqldump \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --user="$DB_USER" \
    --single-transaction \
    --routines \
    --triggers \
    --set-gtid-purged=OFF \
    "$DB_NAME" | gzip -9 > "$FILEPATH"

echo "[backup] Backup complete: $(du -sh "$FILEPATH" | cut -f1) written."

# ── 8. Retention: remove oldest backups beyond the keep limit ────────────────
# Sort by filename (timestamp-prefixed) ascending, delete all but the last N.
mapfile -t OLD_FILES < <(
    ls -1t "${BACKUP_DIR}/${DB_NAME}_"*.sql.gz 2>/dev/null | tail -n +"$((BACKUP_RETAIN + 1))"
)

if [[ ${#OLD_FILES[@]} -gt 0 ]]; then
    echo "[backup] Pruning ${#OLD_FILES[@]} old backup(s):"
    for f in "${OLD_FILES[@]}"; do
        echo "  removing: $f"
        rm -f "$f"
    done
else
    echo "[backup] Retention OK — no old backups to prune."
fi

echo "[backup] Done. Backups retained: $(ls -1 "${BACKUP_DIR}/${DB_NAME}_"*.sql.gz 2>/dev/null | wc -l)"
