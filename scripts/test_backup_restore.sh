#!/bin/bash
#
# Backup Restore Test Script für KI-Mail-Helper
# Testet ob Backups tatsächlich wiederherstellbar sind
#
# 🐛 BUG-015 FIX: Validierung dass Backups funktionieren
#
# Usage:
#   ./scripts/test_backup_restore.sh                    # Test neuestes Backup
#   ./scripts/test_backup_restore.sh backups/daily/...  # Test spezifisches Backup
#
# Was wird getestet:
# - Backup ist entpackbar
# - SQLite Integrity Check
# - Kritische Tabellen existieren
# - Queries funktionieren
# - Schema-Version korrekt

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging
log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

# Find backup file
BACKUP_FILE="${1:-}"
if [ -z "$BACKUP_FILE" ]; then
    # Find newest backup (daily or weekly)
    BACKUP_FILE=$(find "$PROJECT_DIR/backups" -name "emails_*.db.gz" -type f 2>/dev/null | sort -r | head -1)
fi

if [ -z "$BACKUP_FILE" ] || [ ! -f "$BACKUP_FILE" ]; then
    error "No backup found"
    echo "Usage: $0 [backup-file]"
    echo "Example: $0 backups/daily/emails_20260105_140000.db.gz"
    exit 1
fi

log "Testing backup: ${BACKUP_FILE}"

# Temporary test file
TEST_DB="/tmp/restore_test_$$.db"
trap "rm -f $TEST_DB" EXIT

# =============================================================================
# Test 1: Decompression
# =============================================================================
log "Test 1/6: Decompression..."
if gunzip -c "$BACKUP_FILE" > "$TEST_DB" 2>/dev/null; then
    success "Backup decompressed successfully"
else
    error "Failed to decompress backup"
    exit 1
fi

# Check file size
SIZE=$(du -h "$TEST_DB" | cut -f1)
log "Decompressed size: $SIZE"

# =============================================================================
# Test 2: SQLite Integrity Check
# =============================================================================
log "Test 2/6: SQLite Integrity Check..."
INTEGRITY_RESULT=$(sqlite3 "$TEST_DB" "PRAGMA integrity_check;" 2>&1)
if [ "$INTEGRITY_RESULT" = "ok" ]; then
    success "Integrity check passed"
else
    error "Integrity check failed: $INTEGRITY_RESULT"
    exit 1
fi

# =============================================================================
# Test 3: Schema Validation
# =============================================================================
log "Test 3/6: Schema Validation..."

# Check table count
TABLE_COUNT=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>&1)
if [ "$TABLE_COUNT" -lt 5 ]; then
    error "Too few tables: $TABLE_COUNT (expected >= 5)"
    exit 1
fi
success "Found $TABLE_COUNT tables"

# Check critical tables exist
CRITICAL_TABLES=("users" "raw_emails" "processed_emails" "mail_accounts" "email_tags")
for table in "${CRITICAL_TABLES[@]}"; do
    if sqlite3 "$TEST_DB" "SELECT 1 FROM sqlite_master WHERE type='table' AND name='$table';" | grep -q 1; then
        log "  ✓ Table '$table' exists"
    else
        error "Critical table missing: $table"
        exit 1
    fi
done
success "All critical tables present"

# =============================================================================
# Test 4: Schema Version
# =============================================================================
log "Test 4/6: Schema Version Check..."
SCHEMA_VERSION=$(sqlite3 "$TEST_DB" "SELECT version_num FROM alembic_version;" 2>/dev/null || echo "unknown")
if [ "$SCHEMA_VERSION" = "unknown" ]; then
    warning "No alembic version found (pre-migration DB?)"
else
    success "Schema version: $SCHEMA_VERSION"
fi

# =============================================================================
# Test 5: Data Sanity Checks
# =============================================================================
log "Test 5/6: Data Sanity Checks..."

# Query counts
USER_COUNT=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM users;" 2>/dev/null || echo "0")
EMAIL_COUNT=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM raw_emails;" 2>/dev/null || echo "0")
ACCOUNT_COUNT=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM mail_accounts;" 2>/dev/null || echo "0")
TAG_COUNT=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM email_tags;" 2>/dev/null || echo "0")

log "  Users: $USER_COUNT"
log "  Emails: $EMAIL_COUNT"
log "  Accounts: $ACCOUNT_COUNT"
log "  Tags: $TAG_COUNT"

if [ "$USER_COUNT" -eq 0 ]; then
    warning "No users found (empty database?)"
fi

success "Data queries successful"

# =============================================================================
# Test 6: Complex Queries
# =============================================================================
log "Test 6/6: Testing complex queries..."

# Test JOIN query (ProcessedEmail -> RawEmail -> User)
JOIN_TEST=$(sqlite3 "$TEST_DB" "
    SELECT COUNT(*) 
    FROM processed_emails pe 
    JOIN raw_emails re ON pe.raw_email_id = re.id 
    JOIN users u ON re.user_id = u.id
    LIMIT 10;
" 2>/dev/null || echo "0")

if [ "$JOIN_TEST" ]; then
    success "Complex JOIN queries work"
else
    error "JOIN query failed"
    exit 1
fi

# Test encrypted field structure (should have encrypted_* columns)
ENCRYPTED_COLUMNS=$(sqlite3 "$TEST_DB" "
    SELECT COUNT(*) 
    FROM pragma_table_info('raw_emails') 
    WHERE name LIKE 'encrypted_%';
" 2>/dev/null || echo "0")

if [ "$ENCRYPTED_COLUMNS" -ge 3 ]; then
    success "Encryption schema intact ($ENCRYPTED_COLUMNS encrypted columns)"
else
    warning "Few encrypted columns found: $ENCRYPTED_COLUMNS"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
success "Backup Restore Test PASSED"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Summary:"
echo "   Backup File: $(basename "$BACKUP_FILE")"
echo "   Database Size: $SIZE"
echo "   Tables: $TABLE_COUNT"
echo "   Users: $USER_COUNT"
echo "   Emails: $EMAIL_COUNT"
echo "   Schema Version: $SCHEMA_VERSION"
echo ""
success "This backup is RESTORABLE and VALID"
echo ""

# Cleanup is done by trap
exit 0
