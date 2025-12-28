#!/bin/bash
#
# Database Backup Script für KI-Mail-Helper
# Erstellt tägliche Backups von emails.db mit Rotation
#
# Installation:
# chmod +x scripts/backup_database.sh
#
# Crontab (täglich um 2:00 Uhr):
# 0 2 * * * /home/thomas/projects/KI-Mail-Helper/scripts/backup_database.sh
#
# Optional: Wöchentlich um 3:00 Uhr:
# 0 3 * * 0 /home/thomas/projects/KI-Mail-Helper/scripts/backup_database.sh weekly

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DB_FILE="$PROJECT_DIR/emails.db"
BACKUP_DIR="$PROJECT_DIR/backups"
BACKUP_TYPE="${1:-daily}"  # daily or weekly
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30  # Keep backups for 30 days
RETENTION_WEEKLY=90  # Keep weekly backups for 90 days

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Error handling
error_exit() {
    log "ERROR: $1"
    exit 1
}

# Check if database exists
if [ ! -f "$DB_FILE" ]; then
    error_exit "Database not found: $DB_FILE"
fi

# Create backup directory
mkdir -p "$BACKUP_DIR/$BACKUP_TYPE"

# Generate backup filename
if [ "$BACKUP_TYPE" = "weekly" ]; then
    BACKUP_FILE="$BACKUP_DIR/weekly/emails_${DATE}_week$(date +%W).db"
else
    BACKUP_FILE="$BACKUP_DIR/daily/emails_${DATE}.db"
fi

log "Starting backup: $BACKUP_FILE"

# Optional: Checkpoint WAL vor Backup (merged .wal ins .db für sauberere Backups)
# Phase 9e: TRUNCATE deleted .wal/.shm nach Checkpoint
sqlite3 "$DB_FILE" "PRAGMA wal_checkpoint(TRUNCATE);" 2>/dev/null || true

# Create backup using SQLite .backup command (safe for hot backups)
# WAL-aware: Automatisch kopiert .db + .wal + .shm Files atomic (Phase 9d)
sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'" || error_exit "Backup failed"

# Verify backup integrity
log "Verifying backup integrity..."
sqlite3 "$BACKUP_FILE" "PRAGMA integrity_check;" > /dev/null || error_exit "Backup integrity check failed"

# Get backup size
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
log "Backup completed successfully: $BACKUP_SIZE"

# Compress backup (optional - saves space)
log "Compressing backup..."
gzip "$BACKUP_FILE" || log "Warning: Compression failed (backup still valid)"
BACKUP_FILE="${BACKUP_FILE}.gz"

# Cleanup old backups
if [ "$BACKUP_TYPE" = "weekly" ]; then
    RETENTION=$RETENTION_WEEKLY
else
    RETENTION=$RETENTION_DAYS
fi

log "Cleaning up backups older than $RETENTION days..."
find "$BACKUP_DIR/$BACKUP_TYPE" -name "emails_*.db.gz" -mtime +$RETENTION -delete 2>/dev/null || true

# Count remaining backups
BACKUP_COUNT=$(find "$BACKUP_DIR/$BACKUP_TYPE" -name "emails_*.db.gz" | wc -l)
log "Total backups in $BACKUP_TYPE: $BACKUP_COUNT"

# Optional: Upload to remote storage (uncomment and configure)
# log "Uploading to remote storage..."
# rsync -avz "$BACKUP_FILE" user@backup-server:/path/to/backups/
# rclone copy "$BACKUP_FILE" remote:mail-helper-backups/

log "Backup process completed successfully"

# Exit with success
exit 0
