#!/usr/bin/env python3
"""
SQLite Concurrent Access Test
Testet ob WAL Mode concurrent reads während write erlaubt
"""

import sqlite3
import time
import threading
import sys

def writer_thread(db_path: str):
    """Simuliert langen Write (Background-Job)"""
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        cursor = conn.cursor()
        
        # Start Transaction
        cursor.execute("BEGIN EXCLUSIVE")
        print("🔒 WRITER: Transaction gestartet (Lock gehalten)")
        
        # Simuliere lange Verarbeitung
        time.sleep(3)
        
        # Dummy Write
        cursor.execute("CREATE TABLE IF NOT EXISTS test_concurrent (id INTEGER PRIMARY KEY, data TEXT)")
        cursor.execute("INSERT INTO test_concurrent (data) VALUES ('test')")
        conn.commit()
        
        print("✅ WRITER: Transaction committed")
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ WRITER Error: {type(e).__name__}: {e}")


def reader_thread(db_path: str, delay: float):
    """Simuliert Read während Write (Flask Request)"""
    time.sleep(delay)
    
    try:
        start = time.time()
        conn = sqlite3.connect(db_path, timeout=10)
        cursor = conn.cursor()
        
        # Versuche Read während Writer Lock hält
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        result = cursor.fetchone()
        
        elapsed = time.time() - start
        print(f"✅ READER: Read erfolgreich nach {elapsed:.2f}s (Result: {result})")
        
        cursor.close()
        conn.close()
        
    except sqlite3.OperationalError as e:
        elapsed = time.time() - start
        print(f"❌ READER: {e} (nach {elapsed:.2f}s)")
    except Exception as e:
        print(f"❌ READER Error: {type(e).__name__}: {e}")


def test_concurrent_access(db_path: str):
    """Testet concurrent read während write"""
    
    print("\n🧪 Test: Concurrent Read während Write\n")
    print("Szenario: Writer hält Lock für 3 Sekunden")
    print("         Reader versucht Read nach 1 Sekunde\n")
    print("Erwartung (WAL Mode): Reader kann sofort lesen (kein Wait)")
    print("Erwartung (DELETE Mode): Reader wartet oder timeout\n")
    
    # Start Writer (hält Lock 3s)
    writer = threading.Thread(target=writer_thread, args=(db_path,))
    writer.start()
    
    # Start Reader nach 1s (während Writer Lock hält)
    reader = threading.Thread(target=reader_thread, args=(db_path, 1.0))
    reader.start()
    
    # Wait for completion
    writer.join()
    reader.join()
    
    print("\n" + "="*60)


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "emails.db"
    
    # Check WAL Mode first
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    
    print(f"📊 Aktueller journal_mode: {mode}")
    
    if mode.lower() != 'wal':
        print("⚠️  WAL Mode nicht aktiv! Test wird trotzdem durchgeführt...")
    
    test_concurrent_access(db_path)
    
    print("\n✅ Test abgeschlossen")
    print("ℹ️  Bei WAL Mode: Reader sollte SOFORT erfolgreich sein")
    print("ℹ️  Bei DELETE Mode: Reader müsste 3s warten oder timeout")
