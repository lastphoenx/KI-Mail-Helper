"""
Migration: Add Account Lockout columns to User table
Phase 9 - Production Hardening

Adds:
- failed_login_attempts (INTEGER, default 0)
- locked_until (DATETIME, nullable)
- last_failed_login (DATETIME, nullable)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
import importlib
models_module = importlib.import_module('src.02_models')

def migrate():
    """Fügt Account Lockout Spalten zur users Tabelle hinzu"""
    engine, Session = models_module.init_db()
    
    with engine.begin() as conn:
        print("📊 Starte Migration: Account Lockout Columns...")
        
        # Check if columns already exist
        result = conn.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result]
        
        migrations_needed = []
        if 'failed_login_attempts' not in columns:
            migrations_needed.append(
                "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0"
            )
        
        if 'locked_until' not in columns:
            migrations_needed.append(
                "ALTER TABLE users ADD COLUMN locked_until DATETIME"
            )
        
        if 'last_failed_login' not in columns:
            migrations_needed.append(
                "ALTER TABLE users ADD COLUMN last_failed_login DATETIME"
            )
        
        if not migrations_needed:
            print("✅ Alle Spalten existieren bereits - keine Migration notwendig")
            return
        
        # Apply migrations
        for sql in migrations_needed:
            print(f"   Executing: {sql}")
            conn.execute(text(sql))
        
        print(f"✅ {len(migrations_needed)} Spalten hinzugefügt")
        print("\n📋 Account Lockout Features:")
        print("   - 5 fehlgeschlagene Logins → 15 Minuten Sperre")
        print("   - Automatische Entsperrung nach Timeout")
        print("   - Failed Login Counter mit Timestamp")

if __name__ == "__main__":
    migrate()
