#!/usr/bin/env bash
# =============================================================================
# setup_cron.sh — Setup daily automated database backup via cron
#
# Usage:
#   sudo bash scripts/setup_cron.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
APP_NAME="gnaid"

echo "[setup] Configuring daily database backup for $APP_NAME..."

# Detect Python path (prefer venv)
PYTHON_PATH="$REPO_DIR/venv/bin/python"
if [[ ! -f "$PYTHON_PATH" ]]; then
    PYTHON_PATH="$(which python3)"
    echo "[setup] Venv not found, using system Python: $PYTHON_PATH"
else
    echo "[setup] Using venv Python: $PYTHON_PATH"
fi

# Check backup script exists
BACKUP_SCRIPT="$REPO_DIR/scripts/backup_daily.py"
if [[ ! -f "$BACKUP_SCRIPT" ]]; then
    echo "[setup] ERROR: Backup script not found: $BACKUP_SCRIPT"
    exit 1
fi

# Create cron entry
CRON_LINE="0 2 * * * cd $REPO_DIR && $PYTHON_PATH $BACKUP_SCRIPT >> /var/log/${APP_NAME}_backup.log 2>&1"

# Install cron job (remove existing first to avoid duplicates)
(crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT" || true) > /tmp/crontab.tmp
echo "$CRON_LINE" >> /tmp/crontab.tmp
crontab /tmp/crontab.tmp
rm /tmp/crontab.tmp

echo "[setup] Cron job installed:"
echo "  Schedule: Daily at 02:00"
echo "  Command:  $CRON_LINE"
echo "  Log:      /var/log/${APP_NAME}_backup.log"

# Create log file with proper permissions
touch "/var/log/${APP_NAME}_backup.log"
chmod 644 "/var/log/${APP_NAME}_backup.log"

echo "[setup] Cron configuration complete!"
echo ""
echo "To verify:"
echo "  crontab -l"
echo ""
echo "To test backup now:"
echo "  $PYTHON_PATH $BACKUP_SCRIPT"
