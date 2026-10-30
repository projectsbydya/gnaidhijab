#!/usr/bin/env bash
# =============================================================================
# backup_uploads.sh — Daily compressed uploads backup with 7-day retention
#
# Backs up all user-uploaded content into a single timestamped .tar.gz.
# Reads source paths exclusively from environment variables — no hardcoded paths.
#
# Env vars honoured (same defaults as config.py):
#   PRODUCT_UPLOAD_FOLDER   default: <repo>/static/uploads/products
#   BANNER_UPLOAD_FOLDER    default: <repo>/static/images/banners
#   VIDEO_UPLOAD_FOLDER     default: <repo>/static/videos
#
# Optional:
#   UPLOADS_BACKUP_DIR      Where to write archives  (default: <repo>/backups/uploads)
#   BACKUP_RETAIN           How many archives to keep  (default: 7)
#
# Usage:
#   # One-off
#   source .env && bash scripts/backup_uploads.sh
#
#   # Cron — daily at 03:00, after the DB backup
#   0 3 * * * cd /var/www/gnaid && source .env && bash scripts/backup_uploads.sh >> /var/log/gnaid_uploads_backup.log 2>&1
# =============================================================================

set -euo pipefail

# ── 1. Resolve repo root ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# ── 2. Load .env if needed ───────────────────────────────────────────────────
ENV_FILE="${REPO_DIR}/.env"
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    set -a; source "$ENV_FILE"; set +a
fi

# ── 3. Source directories (mirror config.py defaults) ───────────────────────
PRODUCT_UPLOAD_FOLDER="${PRODUCT_UPLOAD_FOLDER:-${REPO_DIR}/static/uploads/products}"
BANNER_UPLOAD_FOLDER="${BANNER_UPLOAD_FOLDER:-${REPO_DIR}/static/images/banners}"
VIDEO_UPLOAD_FOLDER="${VIDEO_UPLOAD_FOLDER:-${REPO_DIR}/static/videos}"

# Collect only directories that actually exist
SOURCE_DIRS=()
for DIR in "$PRODUCT_UPLOAD_FOLDER" "$BANNER_UPLOAD_FOLDER" "$VIDEO_UPLOAD_FOLDER"; do
    if [[ -d "$DIR" ]]; then
        SOURCE_DIRS+=("$DIR")
    else
        echo "[backup-uploads] WARN: directory not found, skipping: $DIR"
    fi
done

if [[ ${#SOURCE_DIRS[@]} -eq 0 ]]; then
    echo "[backup-uploads] ERROR: No upload directories found. Nothing to back up." >&2
    exit 1
fi

# ── 4. Destination ───────────────────────────────────────────────────────────
UPLOADS_BACKUP_DIR="${UPLOADS_BACKUP_DIR:-${REPO_DIR}/backups/uploads}"
BACKUP_RETAIN="${BACKUP_RETAIN:-7}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
FILENAME="uploads_${TIMESTAMP}.tar.gz"
FILEPATH="${UPLOADS_BACKUP_DIR}/${FILENAME}"

mkdir -p "$UPLOADS_BACKUP_DIR"

# ── 5. Create archive ────────────────────────────────────────────────────────
echo "[backup-uploads] Archiving ${#SOURCE_DIRS[@]} director(ies) → ${FILEPATH}"
for DIR in "${SOURCE_DIRS[@]}"; do
    echo "  + ${DIR}"
done

# Use paths relative to REPO_DIR so the archive is portable
RELATIVE_DIRS=()
for DIR in "${SOURCE_DIRS[@]}"; do
    RELATIVE_DIRS+=("$(realpath --relative-to="$REPO_DIR" "$DIR")")
done

tar \
    --create \
    --gzip \
    --file="$FILEPATH" \
    --directory="$REPO_DIR" \
    "${RELATIVE_DIRS[@]}"

SIZE="$(du -sh "$FILEPATH" | cut -f1)"
echo "[backup-uploads] Archive complete: ${SIZE} written."

# ── 6. Retention ─────────────────────────────────────────────────────────────
mapfile -t OLD_FILES < <(
    ls -1t "${UPLOADS_BACKUP_DIR}/uploads_"*.tar.gz 2>/dev/null \
    | tail -n +"$((BACKUP_RETAIN + 1))"
)

if [[ ${#OLD_FILES[@]} -gt 0 ]]; then
    echo "[backup-uploads] Pruning ${#OLD_FILES[@]} old archive(s):"
    for F in "${OLD_FILES[@]}"; do
        echo "  removing: $F"
        rm -f "$F"
    done
else
    echo "[backup-uploads] Retention OK — no old archives to prune."
fi

REMAINING="$(ls -1 "${UPLOADS_BACKUP_DIR}/uploads_"*.tar.gz 2>/dev/null | wc -l)"
echo "[backup-uploads] Done. Archives retained: ${REMAINING}"
