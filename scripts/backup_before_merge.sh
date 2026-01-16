#!/bin/bash
# =============================================================================
# Backup-Script vor Main-Merge
# =============================================================================
# Erstellt vollständige Backups von:
# - Git (Tag auf aktuellem main)
# - SQLite Datenbank (falls vorhanden)
# - PostgreSQL Datenbank
# - .env Konfigurationsdateien
#
# Verwendung:
#   ./scripts/backup_before_merge.sh [backup-name]
#
# Beispiel:
#   ./scripts/backup_before_merge.sh pre-multiuser
# =============================================================================

set -e  # Exit on error

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Konfiguration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_NAME="${1:-pre-main-merge}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/thomas/projects/backups/KI-Mail-Helper-MultiUser/${BACKUP_NAME}_${TIMESTAMP}"

# PostgreSQL Konfiguration (aus .env.local oder .env laden)
load_db_config() {
    if [ -f "$PROJECT_ROOT/.env.local" ]; then
        source <(grep -E '^DATABASE_URL=' "$PROJECT_ROOT/.env.local" | sed 's/^/export /')
    elif [ -f "$PROJECT_ROOT/.env" ]; then
        source <(grep -E '^DATABASE_URL=' "$PROJECT_ROOT/.env" | sed 's/^/export /')
    fi
    
    # Parse DATABASE_URL: postgresql://user:pass@host:port/dbname
    if [ -n "$DATABASE_URL" ]; then
        # Extract components
        DB_USER=$(echo "$DATABASE_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
        DB_PASS=$(echo "$DATABASE_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
        DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
        DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
        DB_NAME=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')
    fi
}

echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}  Mail-Helper Backup Script${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""
echo -e "Backup-Name: ${GREEN}${BACKUP_NAME}_${TIMESTAMP}${NC}"
echo -e "Zielordner:  ${GREEN}${BACKUP_DIR}${NC}"
echo ""

# Backup-Verzeichnis erstellen
mkdir -p "$BACKUP_DIR"

# =============================================================================
# 1. Git Tag erstellen
# =============================================================================
echo -e "${YELLOW}[1/5] Git Tag erstellen...${NC}"

cd "$PROJECT_ROOT"

# Prüfen ob wir auf main sind oder main existiert
if git rev-parse --verify main >/dev/null 2>&1; then
    MAIN_COMMIT=$(git rev-parse main)
    TAG_NAME="${BACKUP_NAME}-main-${TIMESTAMP}"
    
    # Tag erstellen
    git tag -a "$TAG_NAME" main -m "Backup vor Merge: $BACKUP_NAME ($TIMESTAMP)"
    
    echo -e "  ${GREEN}✓${NC} Git Tag erstellt: ${GREEN}$TAG_NAME${NC}"
    echo -e "  ${GREEN}✓${NC} Main Commit: ${GREEN}$MAIN_COMMIT${NC}"
    
    # Tag-Info speichern
    echo "tag_name=$TAG_NAME" > "$BACKUP_DIR/git_info.txt"
    echo "main_commit=$MAIN_COMMIT" >> "$BACKUP_DIR/git_info.txt"
    echo "feature_branch=$(git branch --show-current)" >> "$BACKUP_DIR/git_info.txt"
    echo "feature_commit=$(git rev-parse HEAD)" >> "$BACKUP_DIR/git_info.txt"
    echo "timestamp=$TIMESTAMP" >> "$BACKUP_DIR/git_info.txt"
else
    echo -e "  ${YELLOW}⚠${NC} Main-Branch nicht gefunden, überspringe Git-Tag"
fi

# =============================================================================
# 2. SQLite Backup (falls vorhanden)
# =============================================================================
echo -e "${YELLOW}[2/5] SQLite Backup...${NC}"

SQLITE_FILES=$(find "$PROJECT_ROOT" -maxdepth 1 -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" 2>/dev/null || true)

if [ -n "$SQLITE_FILES" ]; then
    mkdir -p "$BACKUP_DIR/sqlite"
    for db_file in $SQLITE_FILES; do
        if [ -f "$db_file" ]; then
            filename=$(basename "$db_file")
            cp "$db_file" "$BACKUP_DIR/sqlite/$filename"
            echo -e "  ${GREEN}✓${NC} Gesichert: $filename"
        fi
    done
else
    echo -e "  ${BLUE}ℹ${NC} Keine SQLite-Datenbanken gefunden"
fi

# =============================================================================
# 3. PostgreSQL Backup
# =============================================================================
echo -e "${YELLOW}[3/5] PostgreSQL Backup...${NC}"

load_db_config

if [ -n "$DATABASE_URL" ] && [ -n "$DB_NAME" ]; then
    mkdir -p "$BACKUP_DIR/postgresql"
    
    PGDUMP_FILE="$BACKUP_DIR/postgresql/${DB_NAME}_${TIMESTAMP}.sql"
    
    # pg_dump ausführen
    export PGPASSWORD="$DB_PASS"
    
    if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
               --no-owner --no-privileges \
               -f "$PGDUMP_FILE" 2>/dev/null; then
        
        # Komprimieren
        gzip "$PGDUMP_FILE"
        
        echo -e "  ${GREEN}✓${NC} PostgreSQL Dump erstellt: ${DB_NAME}"
        echo -e "  ${GREEN}✓${NC} Datei: $(basename ${PGDUMP_FILE}.gz)"
        
        # Statistiken
        TABLE_COUNT=$(PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo "?")
        echo -e "  ${BLUE}ℹ${NC} Tabellen: $TABLE_COUNT"
        
        # DB-Info speichern
        echo "database=$DB_NAME" > "$BACKUP_DIR/postgresql/db_info.txt"
        echo "host=$DB_HOST" >> "$BACKUP_DIR/postgresql/db_info.txt"
        echo "port=$DB_PORT" >> "$BACKUP_DIR/postgresql/db_info.txt"
        echo "user=$DB_USER" >> "$BACKUP_DIR/postgresql/db_info.txt"
        echo "tables=$TABLE_COUNT" >> "$BACKUP_DIR/postgresql/db_info.txt"
    else
        echo -e "  ${RED}✗${NC} PostgreSQL Dump fehlgeschlagen"
        echo -e "  ${YELLOW}⚠${NC} Prüfe Verbindungsdaten in .env.local"
    fi
    
    unset PGPASSWORD
else
    echo -e "  ${BLUE}ℹ${NC} Keine PostgreSQL-Konfiguration gefunden (DATABASE_URL)"
fi

# =============================================================================
# 4. Konfigurationsdateien sichern
# =============================================================================
echo -e "${YELLOW}[4/5] Konfigurationsdateien sichern...${NC}"

mkdir -p "$BACKUP_DIR/config"

# .env Dateien (ohne Passwörter im Log)
for env_file in .env .env.local .env.production; do
    if [ -f "$PROJECT_ROOT/$env_file" ]; then
        cp "$PROJECT_ROOT/$env_file" "$BACKUP_DIR/config/$env_file"
        echo -e "  ${GREEN}✓${NC} Gesichert: $env_file"
    fi
done

# Alembic Version
if [ -f "$PROJECT_ROOT/alembic.ini" ]; then
    cp "$PROJECT_ROOT/alembic.ini" "$BACKUP_DIR/config/"
    echo -e "  ${GREEN}✓${NC} Gesichert: alembic.ini"
fi

# Aktuelle Alembic Revision speichern
if command -v alembic &> /dev/null; then
    cd "$PROJECT_ROOT"
    CURRENT_REV=$(alembic current 2>/dev/null | head -1 || echo "unknown")
    echo "alembic_revision=$CURRENT_REV" >> "$BACKUP_DIR/config/migration_state.txt"
    echo -e "  ${GREEN}✓${NC} Alembic Revision: $CURRENT_REV"
fi

# =============================================================================
# 5. Restore-Script erstellen
# =============================================================================
echo -e "${YELLOW}[5/5] Restore-Script erstellen...${NC}"

cat > "$BACKUP_DIR/RESTORE.sh" << 'RESTORE_EOF'
#!/bin/bash
# =============================================================================
# Restore-Script für Mail-Helper Backup
# =============================================================================
# ACHTUNG: Dieses Script überschreibt aktuelle Daten!
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR"

echo "============================================="
echo "  Mail-Helper RESTORE Script"
echo "============================================="
echo ""
echo "WARNUNG: Dies überschreibt alle aktuellen Daten!"
echo ""
read -p "Fortfahren? (ja/nein): " CONFIRM

if [ "$CONFIRM" != "ja" ]; then
    echo "Abgebrochen."
    exit 1
fi

# Git restore
if [ -f "$BACKUP_DIR/git_info.txt" ]; then
    source "$BACKUP_DIR/git_info.txt"
    echo ""
    echo "Git Restore-Optionen:"
    echo "  1. git checkout $tag_name     # Zum Tag wechseln"
    echo "  2. git reset --hard $main_commit  # Main zurücksetzen"
    echo ""
fi

# PostgreSQL restore
if [ -d "$BACKUP_DIR/postgresql" ]; then
    SQL_FILE=$(ls "$BACKUP_DIR/postgresql/"*.sql.gz 2>/dev/null | head -1)
    if [ -n "$SQL_FILE" ]; then
        echo "PostgreSQL Restore:"
        echo "  1. gunzip -k $SQL_FILE"
        echo "  2. psql -U mail_helper -d mail_helper < ${SQL_FILE%.gz}"
        echo ""
    fi
fi

# SQLite restore
if [ -d "$BACKUP_DIR/sqlite" ]; then
    echo "SQLite Restore:"
    echo "  cp $BACKUP_DIR/sqlite/*.db /pfad/zum/projekt/"
    echo ""
fi

echo "Restore-Anweisungen ausgegeben. Bitte manuell ausführen."
RESTORE_EOF

chmod +x "$BACKUP_DIR/RESTORE.sh"
echo -e "  ${GREEN}✓${NC} Restore-Script erstellt"

# =============================================================================
# Zusammenfassung
# =============================================================================
echo ""
echo -e "${BLUE}=============================================${NC}"
echo -e "${GREEN}  Backup erfolgreich erstellt!${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""
echo -e "Backup-Verzeichnis: ${GREEN}$BACKUP_DIR${NC}"
echo ""

# Größe anzeigen
BACKUP_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
echo -e "Gesamtgröße: ${GREEN}$BACKUP_SIZE${NC}"
echo ""

# Inhalt auflisten
echo "Inhalt:"
ls -la "$BACKUP_DIR"
echo ""

echo -e "${YELLOW}Nächste Schritte:${NC}"
echo "  1. Backup prüfen: ls -la $BACKUP_DIR"
echo "  2. Merge durchführen:"
echo "     git checkout main"
echo "     git merge feature/multi-user-native"
echo "     git push origin main"
echo ""
echo -e "${YELLOW}Bei Problemen zurückkehren:${NC}"
echo "  $BACKUP_DIR/RESTORE.sh"
echo ""
