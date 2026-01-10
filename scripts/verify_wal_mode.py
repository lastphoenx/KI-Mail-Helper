#!/usr/bin/env python3
"""
SQLite WAL Mode Verification Script
Prüft ob WAL Mode + busy_timeout korrekt aktiviert sind
"""

import sqlite3
import sys
import os

def verify_wal_mode(db_path: str):
    """Verifiziert SQLite WAL-Konfiguration"""
    
    if not os.path.exists(db_path):
        print(f"❌ Datenbank nicht gefunden: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check journal_mode
        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0].lower()
        
        # Check busy_timeout
        cursor.execute("PRAGMA busy_timeout;")
        busy_timeout = cursor.fetchone()[0]
        
        # Check wal_autocheckpoint
        cursor.execute("PRAGMA wal_autocheckpoint;")
        wal_checkpoint = cursor.fetchone()[0]
        
        # Check synchronous (Phase 9e)
        cursor.execute("PRAGMA synchronous;")
        synchronous = cursor.fetchone()[0]
        
        # Check foreign_keys
        cursor.execute("PRAGMA foreign_keys;")
        foreign_keys = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        # Verify Values
        print("\n📊 SQLite Configuration:")
        print(f"  journal_mode:        {journal_mode} {'✅' if journal_mode == 'wal' else '❌ (expected: wal)'}")
        print(f"  busy_timeout:        {busy_timeout}ms {'✅' if busy_timeout == 5000 else f'⚠️  (expected: 5000ms)'}")
        print(f"  wal_autocheckpoint:  {wal_checkpoint} pages {'✅' if wal_checkpoint == 1000 else f'⚠️  (expected: 1000)'}")
        print(f"  synchronous:         {synchronous} {'✅ (NORMAL)' if synchronous == 1 else f'ℹ️  (per-connection setting, app setzt NORMAL)'}")
        print(f"  foreign_keys:        {'ON' if foreign_keys else 'OFF'} {'✅' if foreign_keys else 'ℹ️  (per-connection setting)'}")
        
        # Check WAL files
        wal_file = f"{db_path}-wal"
        shm_file = f"{db_path}-shm"
        
        print("\n📁 WAL Files:")
        if os.path.exists(wal_file):
            size = os.path.getsize(wal_file)
            print(f"  {wal_file}: {size} bytes ✅")
        else:
            print(f"  {wal_file}: Noch nicht erstellt (wird bei erstem Write angelegt) ℹ️")
        
        if os.path.exists(shm_file):
            size = os.path.getsize(shm_file)
            print(f"  {shm_file}: {size} bytes ✅")
        else:
            print(f"  {shm_file}: Noch nicht erstellt (wird bei erstem Write angelegt) ℹ️")
        
        # Final Result (ignore per-connection PRAGMAs)
        all_good = (
            journal_mode == 'wal' and
            busy_timeout == 5000 and
            wal_checkpoint == 1000
        )
        
        if all_good:
            print("\n✅ SQLite WAL Mode korrekt konfiguriert!")
            print("   → Concurrent Reads möglich")
            print("   → Deadlock-Risiko minimiert")
            return True
        else:
            print("\n⚠️  Konfiguration nicht optimal")
            print("   → Starte Applikation neu für automatische Migration")
            return False
            
    except Exception as e:
        print(f"❌ Fehler beim Prüfen: {type(e).__name__}")
        return False


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "emails.db"
    
    print(f"🔍 Prüfe SQLite-Konfiguration: {db_path}\n")
    
    success = verify_wal_mode(db_path)
    sys.exit(0 if success else 1)
