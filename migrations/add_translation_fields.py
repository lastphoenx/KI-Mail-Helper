"""
Migration: Add Translation Fields to RawEmail
==============================================

Fügt Phase 26 Auto-Translation Felder hinzu:
- detected_language: Erkannte Sprache (ISO-Code)
- encrypted_translation_de: Verschlüsselte deutsche Übersetzung
- translation_engine: Verwendetes Übersetzungsmodell

Usage:
    python migrations/add_translation_fields.py
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.helpers.database import get_session
from sqlalchemy import text

def migrate():
    """Add translation fields to raw_emails table"""
    session = get_session()
    
    try:
        print("🔄 Starting migration: add_translation_fields (PostgreSQL)")
        
        # PostgreSQL: Check if columns already exist
        result = session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'raw_emails'
        """))
        columns = [row[0] for row in result.fetchall()]
        
        migrations_needed = []
        
        if 'detected_language' not in columns:
            migrations_needed.append(
                "ALTER TABLE raw_emails ADD COLUMN detected_language VARCHAR(5)"
            )
            print("  ➕ detected_language column missing")
        else:
            print("  ✓ detected_language already exists")
        
        if 'encrypted_translation_de' not in columns:
            migrations_needed.append(
                "ALTER TABLE raw_emails ADD COLUMN encrypted_translation_de TEXT"
            )
            print("  ➕ encrypted_translation_de column missing")
        else:
            print("  ✓ encrypted_translation_de already exists")
        
        if 'translation_engine' not in columns:
            migrations_needed.append(
                "ALTER TABLE raw_emails ADD COLUMN translation_engine VARCHAR(30)"
            )
            print("  ➕ translation_engine column missing")
        else:
            print("  ✓ translation_engine already exists")
        
        if not migrations_needed:
            print("✅ All columns already exist - nothing to do")
            return True
        
        # Execute migrations
        for sql in migrations_needed:
            print(f"  🔧 Executing: {sql}")
            session.execute(text(sql))
        
        session.commit()
        
        # Create index on detected_language for filtering (PostgreSQL syntax)
        try:
            session.execute(text("CREATE INDEX IF NOT EXISTS ix_raw_emails_detected_language ON raw_emails(detected_language)"))
            session.commit()
            print("  📊 Index on detected_language created")
        except Exception as idx_err:
            print(f"  ⚠️ Index creation skipped (may already exist): {idx_err}")
        
        print("✅ Migration completed successfully")
        return True
        
    except Exception as e:
        session.rollback()
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        session.close()


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
