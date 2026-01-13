#!/usr/bin/env python3
"""
DB Structure – Zeigt die Struktur aller Datenbanken im Projekt.

Listet auf:
- Alle .db Dateien (SQLite Datenbanken)
- Pro DB alle Tabellen
- Pro Tabelle alle Felder mit Typ

Verwendung:
  python3 scripts/db_structure.py           # Alle DBs im Projektordner
  python3 scripts/db_structure.py emails.db # Nur eine bestimmte DB
  python3 scripts/db_structure.py --compact # Kompakte Ausgabe (nur Feldnamen)
  python3 scripts/db_structure.py --list-dbs # Nur Datenbank-Namen auflisten
"""

import sys
import os
import sqlite3
import argparse
from pathlib import Path


def get_table_info(cursor, table_name):
    """Holt Spalteninformationen für eine Tabelle"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    # columns = [(cid, name, type, notnull, dflt_value, pk), ...]
    return columns


def get_foreign_keys(cursor, table_name):
    """Holt Foreign Key Informationen für eine Tabelle"""
    cursor.execute(f"PRAGMA foreign_key_list({table_name})")
    return cursor.fetchall()


def get_indexes(cursor, table_name):
    """Holt Index Informationen für eine Tabelle"""
    cursor.execute(f"PRAGMA index_list({table_name})")
    return cursor.fetchall()


def analyze_database(db_path, compact=False):
    """Analysiert eine SQLite-Datenbank und gibt die Struktur aus"""
    
    if not os.path.exists(db_path):
        print(f"❌ Datenbank nicht gefunden: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Tabellenliste holen (ohne sqlite_ interne Tabellen)
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        # DB-Größe
        db_size = os.path.getsize(db_path)
        if db_size >= 1024 * 1024:
            size_str = f"{db_size / (1024*1024):.1f} MB"
        elif db_size >= 1024:
            size_str = f"{db_size / 1024:.1f} KB"
        else:
            size_str = f"{db_size} Bytes"
        
        print(f"\n📁 Datenbank: {db_path}")
        print(f"   Größe: {size_str} | Tabellen: {len(tables)}")
        print("=" * 80)
        
        total_columns = 0
        
        for table in tables:
            columns = get_table_info(cursor, table)
            fkeys = get_foreign_keys(cursor, table)
            indexes = get_indexes(cursor, table)
            
            # Zeilenanzahl
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cursor.fetchone()[0]
            
            total_columns += len(columns)
            
            if compact:
                # Kompakte Ausgabe: Nur Feldnamen
                col_names = [col[1] for col in columns]
                print(f"\n📋 {table} ({row_count} rows)")
                print(f"   {', '.join(col_names)}")
            else:
                # Ausführliche Ausgabe
                print(f"\n📋 Tabelle: {table}")
                print(f"   Zeilen: {row_count} | Spalten: {len(columns)} | Indexes: {len(indexes)}")
                print("-" * 60)
                
                for col in columns:
                    cid, name, col_type, notnull, default, is_pk = col
                    
                    # Flags sammeln
                    flags = []
                    if is_pk:
                        flags.append("PK")
                    if notnull:
                        flags.append("NOT NULL")
                    
                    # Foreign Key?
                    for fk in fkeys:
                        if fk[3] == name:  # fk[3] = from column
                            flags.append(f"FK→{fk[2]}.{fk[4]}")  # table.column
                    
                    # Index?
                    for idx in indexes:
                        cursor.execute(f"PRAGMA index_info({idx[1]})")
                        idx_cols = cursor.fetchall()
                        for idx_col in idx_cols:
                            if idx_col[2] == name:
                                if idx[2]:  # unique
                                    flags.append("UNIQUE")
                                else:
                                    flags.append("IDX")
                    
                    flags_str = f" [{', '.join(flags)}]" if flags else ""
                    default_str = f" = {default}" if default else ""
                    
                    print(f"   {name:<35} {col_type:<15}{flags_str}{default_str}")
        
        print("\n" + "=" * 80)
        print(f"📊 Zusammenfassung: {len(tables)} Tabellen, {total_columns} Spalten")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Fehler beim Lesen von {db_path}: {e}")
        import traceback
        traceback.print_exc()
        return False


def find_databases(search_path):
    """Findet alle .db Dateien im angegebenen Pfad"""
    db_files = []
    
    # Im Hauptverzeichnis suchen (nicht rekursiv in allen Unterordnern)
    search_dir = Path(search_path)
    
    # Direkt im Verzeichnis
    for db_file in search_dir.glob("*.db"):
        if db_file.is_file():
            db_files.append(str(db_file))
    
    # Auch in data/ falls vorhanden
    data_dir = search_dir / "data"
    if data_dir.exists():
        for db_file in data_dir.glob("*.db"):
            if db_file.is_file():
                db_files.append(str(db_file))
    
    return sorted(db_files)


def main():
    parser = argparse.ArgumentParser(
        description="Zeigt die Struktur aller SQLite-Datenbanken im Projekt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python3 scripts/db_structure.py              # Alle DBs im Projektordner
  python3 scripts/db_structure.py emails.db    # Nur emails.db
  python3 scripts/db_structure.py --compact    # Kompakte Ausgabe
  python3 scripts/db_structure.py --list-dbs   # Nur Datenbank-Namen
  python3 scripts/db_structure.py emails.db --compact
        """
    )
    parser.add_argument('database', nargs='?', help='Spezifische Datenbank-Datei (optional)')
    parser.add_argument('--compact', '-c', action='store_true', help='Kompakte Ausgabe (nur Feldnamen)')
    parser.add_argument('--list-dbs', '-l', action='store_true', help='Nur Datenbank-Namen auflisten (ohne Tabellen/Felder)')
    
    args = parser.parse_args()
    
    print("🗄️  DB Structure Tool")
    print("=" * 80)
    
    # Projektverzeichnis bestimmen
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Wenn --list-dbs, nur DB-Namen auflisten
    if args.list_dbs:
        db_files = find_databases(project_dir)
        if not db_files:
            print(f"ℹ️  Keine .db Dateien gefunden in {project_dir}")
            sys.exit(0)
        
        print(f"Gefundene Datenbanken: {len(db_files)}\n")
        print(f"{'#':<4} {'Dateiname':<30} {'Größe':<12} {'Pfad'}")
        print("-" * 80)
        
        for i, db_path in enumerate(db_files, 1):
            filename = os.path.basename(db_path)
            db_size = os.path.getsize(db_path)
            if db_size >= 1024 * 1024:
                size_str = f"{db_size / (1024*1024):.1f} MB"
            elif db_size >= 1024:
                size_str = f"{db_size / 1024:.1f} KB"
            else:
                size_str = f"{db_size} Bytes"
            
            # Relativer Pfad zum Projekt
            rel_path = os.path.relpath(db_path, project_dir)
            print(f"{i:<4} {filename:<30} {size_str:<12} {rel_path}")
        
        print()
        sys.exit(0)
    
    if args.database:
        # Spezifische DB
        db_path = args.database
        if not os.path.isabs(db_path):
            db_path = os.path.join(project_dir, db_path)
        
        success = analyze_database(db_path, compact=args.compact)
    else:
        # Alle DBs finden
        db_files = find_databases(project_dir)
        
        if not db_files:
            print(f"ℹ️  Keine .db Dateien gefunden in {project_dir}")
            sys.exit(0)
        
        print(f"Gefundene Datenbanken: {len(db_files)}")
        
        success = True
        for db_path in db_files:
            if not analyze_database(db_path, compact=args.compact):
                success = False
    
    print()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
