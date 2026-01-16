════════════════════════════════════════════════════════════════════════
PROBLEM IDENTIFIZIERT - EMAIL-TABS SIND LEER
════════════════════════════════════════════════════════════════════════

TEMPLATE (email_detail.html:208, 227):
───────────────────────────────────────────────────────────────────────
<pre><code>{{ decrypted_body|default('Kein Original verfügbar') }}</code></pre>

Das ist RICHTIG - das Template zeigt `decrypted_body`.

ABER: Warum ist `decrypted_body` LEER?

════════════════════════════════════════════════════════════════════════
MÖGLICHE URSACHEN:
════════════════════════════════════════════════════════════════════════

1. `master_key` = None (nicht in Session)
   ➜ Dann bleibt decrypted_body = "" (Zeile 656 in emails.py)
   ➜ if master_key: (Zeile 663) skipped
   ➜ Template zeigt: "Kein Original verfügbar" oder LEER

2. `raw.encrypted_body` = None
   ➜ decrypt_email_body("", key) schlägt fehl
   ➜ decrypted_body = "(Entschlüsselung fehlgeschlagen)"

3. `raw` ist nicht vollständig geladen
   ➜ raw.encrypted_body existiert nicht (VORHER PROBLEM!)
   ➜ Jetzt SOLLTE BEHOBEN SEIN durch DB-Session-Fix

════════════════════════════════════════════════════════════════════════
VERMUTUNG: master_key fehlt in der Session
════════════════════════════════════════════════════════════════════════

Zeile 650 in emails.py:
  master_key = session.get("master_key")

Frage: Wird master_key ÜBERHAUPT in die Flask-Session geschrieben
beim Login/bei der Authentifizierung?

Das ist NICHT Teil unserer Fixes. Das ist ein ANDERES System.

════════════════════════════════════════════════════════════════════════
#!/bin/bash
# =============================================================================
# rename_legacy_files.sh
# Fügt "legacy_" als Prefix zu allen Dateien im /legacy_restore Ordner hinzu
# (außer .md Dateien)
# =============================================================================

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Standard: Dry-Run aktiviert
DRY_RUN=true
VERBOSE=false
TARGET_DIR=""

# Usage
usage() {
    echo ""
    echo "Usage: $0 [OPTIONS] <target_directory>"
    echo ""
    echo "Fügt 'legacy_' als Prefix zu allen Dateien hinzu (außer .md)"
    echo ""
    echo "OPTIONS:"
    echo "  -x, --execute    Tatsächlich umbenennen (ohne = Dry-Run)"
    echo "  -v, --verbose    Ausführliche Ausgabe"
    echo "  -h, --help       Diese Hilfe anzeigen"
    echo ""
    echo "BEISPIELE:"
    echo "  $0 ./legacy_restore              # Dry-Run (zeigt was passieren würde)"
    echo "  $0 -x ./legacy_restore           # Tatsächlich umbenennen"
    echo "  $0 -x -v ./legacy_restore        # Umbenennen mit Details"
    echo ""
    exit 1
}

# Argument Parsing
while [[ $# -gt 0 ]]; do
    case $1 in
        -x|--execute)
            DRY_RUN=false
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        -*)
            echo -e "${RED}❌ Unbekannte Option: $1${NC}"
            usage
            ;;
        *)
            TARGET_DIR="$1"
            shift
            ;;
    esac
done

# Prüfe ob Zielverzeichnis angegeben
if [[ -z "$TARGET_DIR" ]]; then
    echo -e "${RED}❌ Kein Zielverzeichnis angegeben!${NC}"
    usage
fi

# Prüfe ob Zielverzeichnis existiert
if [[ ! -d "$TARGET_DIR" ]]; then
    echo -e "${RED}❌ Verzeichnis existiert nicht: $TARGET_DIR${NC}"
    exit 1
fi

# Header
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Legacy File Renamer - Prefix 'legacy_' hinzufügen"
echo "═══════════════════════════════════════════════════════════════"
echo ""

if $DRY_RUN; then
    echo -e "${YELLOW}🔍 DRY-RUN MODUS (keine Änderungen werden durchgeführt)${NC}"
    echo -e "${YELLOW}   Verwende -x oder --execute zum tatsächlichen Umbenennen${NC}"
else
    echo -e "${GREEN}🚀 EXECUTE MODUS (Dateien werden umbenannt!)${NC}"
fi
echo ""
echo -e "Zielverzeichnis: ${BLUE}$TARGET_DIR${NC}"
echo ""

# Zähler
renamed_count=0
skipped_md=0
already_prefixed=0
error_count=0

# Finde alle Dateien (keine Verzeichnisse, keine .md)
while IFS= read -r -d '' file; do
    # Extrahiere Verzeichnis und Dateiname
    dir=$(dirname "$file")
    filename=$(basename "$file")
    extension="${filename##*.}"
    
    # Skip .md Dateien
    if [[ "$extension" == "md" ]]; then
        ((skipped_md++))
        if $VERBOSE; then
            echo -e "${YELLOW}⏭️  Skip (Markdown): $file${NC}"
        fi
        continue
    fi
    
    # Skip wenn bereits "legacy_" Prefix hat
    if [[ "$filename" == legacy_* ]]; then
        ((already_prefixed++))
        if $VERBOSE; then
            echo -e "${BLUE}⏭️  Skip (bereits prefixed): $file${NC}"
        fi
        continue
    fi
    
    # Neuer Dateiname
    new_filename="legacy_${filename}"
    new_path="${dir}/${new_filename}"
    
    # Prüfe ob Zieldatei bereits existiert
    if [[ -e "$new_path" ]]; then
        echo -e "${RED}⚠️  Ziel existiert bereits: $new_path${NC}"
        ((error_count++))
        continue
    fi
    
    # Umbenennen oder anzeigen
    if $DRY_RUN; then
        echo -e "  ${GREEN}→${NC} $filename ${GREEN}→${NC} $new_filename"
        if $VERBOSE; then
            echo -e "    ${BLUE}Pfad: $dir/${NC}"
        fi
    else
        if mv "$file" "$new_path" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} $filename ${GREEN}→${NC} $new_filename"
            if $VERBOSE; then
                echo -e "    ${BLUE}Pfad: $dir/${NC}"
            fi
        else
            echo -e "${RED}❌ Fehler beim Umbenennen: $file${NC}"
            ((error_count++))
            continue
        fi
    fi
    
    ((renamed_count++))
    
done < <(find "$TARGET_DIR" -type f -print0 | sort -z)

# Summary
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ZUSAMMENFASSUNG"
echo "═══════════════════════════════════════════════════════════════"
echo ""

if $DRY_RUN; then
    echo -e "  ${GREEN}Würden umbenannt werden:${NC} $renamed_count Dateien"
else
    echo -e "  ${GREEN}Umbenannt:${NC}               $renamed_count Dateien"
fi

echo -e "  ${YELLOW}Übersprungen (Markdown):${NC} $skipped_md Dateien"
echo -e "  ${BLUE}Bereits prefixed:${NC}        $already_prefixed Dateien"

if [[ $error_count -gt 0 ]]; then
    echo -e "  ${RED}Fehler:${NC}                  $error_count Dateien"
fi

echo ""

if $DRY_RUN && [[ $renamed_count -gt 0 ]]; then
    echo -e "${YELLOW}💡 Zum tatsächlichen Umbenennen: $0 -x $TARGET_DIR${NC}"
    echo ""
fi

exit 0
