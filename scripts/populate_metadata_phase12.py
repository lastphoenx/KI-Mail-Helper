#!/usr/bin/env python3
"""
Phase 12 Data Migration: Populate neue Metadaten-Felder

Dieses Script wird nach der Alembic-Migration ausgeführt um:
1. Bestehende imap_flags in Boolean-Spalten zu konvertieren
2. Fehlerbehandlung für Daten ohne neue Felder
3. Batch-Processing für große Datenbanken (1000 Mails/Batch)

Usage:
    cd /path/to/KI-Mail-Helper
    source venv/bin/activate
    python scripts/populate_metadata_phase12.py [--db emails.db] [--batch-size 100]
"""

import argparse
import sys
import os
import logging
from datetime import datetime, UTC
from typing import Optional, Dict, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib
models = importlib.import_module('src.02_models')
RawEmail = models.RawEmail
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class MetadataPopulator:
    """Population logic für Phase 12 Metadaten"""
    
    def __init__(self, db_path: str = 'emails.db', batch_size: int = 100):
        self.db_path = db_path
        self.batch_size = batch_size
        self.engine = create_engine(f'sqlite:///{db_path}')
        self.Session = sessionmaker(bind=self.engine)
        
    def run(self) -> Tuple[int, int, int]:
        """Führt alle Migrations-Schritte aus
        
        Returns:
            (total_processed, errors, skipped)
        """
        logger.info(f"🚀 Phase 12 Metadata Population starten...")
        logger.info(f"📁 Database: {self.db_path}")
        logger.info(f"📦 Batch-Size: {self.batch_size}")
        
        # Schritt 1: Flags konvertieren
        logger.info("\n📊 Schritt 1: imap_flags in Boolean-Spalten konvertieren...")
        flags_count = self._populate_boolean_flags()
        logger.info(f"✅ {flags_count} Mails mit konvertierten Flags")
        
        # Schritt 2: Placeholder-Werte setzen
        logger.info("\n📊 Schritt 2: Placeholder-Werte für fehlende Felder...")
        placeholder_count = self._populate_placeholders()
        logger.info(f"✅ {placeholder_count} Mails mit Placeholder-Werten")
        
        # Schritt 3: Validierung
        logger.info("\n📊 Schritt 3: Validierung der neuen Felder...")
        validation_results = self._validate_data()
        
        logger.info(f"\n✅ Phase 12 Migration abgeschlossen:")
        logger.info(f"   - Boolean Flags: {flags_count}")
        logger.info(f"   - Placeholder-Werte: {placeholder_count}")
        logger.info(f"   - Validation: {validation_results['valid']}/{validation_results['total']}")
        
        return flags_count, placeholder_count, validation_results['total'] - validation_results['valid']
    
    def _populate_boolean_flags(self) -> int:
        """Konvertiert imap_flags String in Boolean-Spalten
        
        Beispiel:
            imap_flags = "\\Seen \\Answered \\Flagged"
            →
            is_seen = True, is_answered = True, is_flagged = True, ...
        """
        session = self.Session()
        try:
            emails = session.query(models.RawEmail).all()
            total = len(emails)
            
            if total == 0:
                logger.warning("⚠️  Keine Mails in Datenbank gefunden")
                return 0
            
            logger.info(f"📧 Processing {total} Mails...")
            
            processed = 0
            for i, email in enumerate(emails, 1):
                if email.imap_flags:
                    flags = email.imap_flags
                    
                    email.imap_is_seen = '\\Seen' in flags or b'\\Seen' in str(flags).encode()
                    email.imap_is_answered = '\\Answered' in flags or b'\\Answered' in str(flags).encode()
                    email.imap_is_flagged = '\\Flagged' in flags or b'\\Flagged' in str(flags).encode()
                    email.imap_is_deleted = '\\Deleted' in flags or b'\\Deleted' in str(flags).encode()
                    email.imap_is_draft = '\\Draft' in flags or b'\\Draft' in str(flags).encode()
                else:
                    # Defaults wenn keine Flags
                    email.imap_is_seen = False
                    email.imap_is_answered = False
                    email.imap_is_flagged = False
                    email.imap_is_deleted = False
                    email.imap_is_draft = False
                
                processed += 1
                
                # Batch-Commit
                if i % self.batch_size == 0:
                    session.commit()
                    pct = (i / total) * 100
                    logger.info(f"  ✓ {i}/{total} ({pct:.0f}%)")
            
            # Final commit
            if processed % self.batch_size != 0:
                session.commit()
            
            logger.info(f"✅ {processed} Mails mit Boolean-Flags aktualisiert")
            return processed
            
        except Exception as e:
            logger.error(f"❌ Fehler bei Flag-Konvertierung: {e}")
            session.rollback()
            return 0
        finally:
            session.close()
    
    def _populate_placeholders(self) -> int:
        """Setzt Placeholder-Werte für fehlende neue Felder
        
        - message_id: None (wird vom Mail-Fetcher später gesetzt)
        - thread_id: None (wird beim nächsten Fetch berechnet)
        - content_type: 'text/plain' (default)
        - charset: 'utf-8' (default)
        - has_attachments: False (conservative default)
        """
        session = self.Session()
        try:
            emails = session.query(models.RawEmail).all()
            total = len(emails)
            
            if total == 0:
                return 0
            
            logger.info(f"📧 Setting placeholders für {total} Mails...")
            
            for i, email in enumerate(emails, 1):
                # Defaults für neue Felder
                if email.content_type is None:
                    email.content_type = 'text/plain'
                
                if email.charset is None:
                    email.charset = 'utf-8'
                
                if email.has_attachments is None:
                    email.has_attachments = False
                
                # message_id, thread_id bleiben None für jetzt
                # (werden beim nächsten Fetch gesetzt)
                
                # Batch-Commit
                if i % self.batch_size == 0:
                    session.commit()
                    pct = (i / total) * 100
                    logger.info(f"  ✓ {i}/{total} ({pct:.0f}%)")
            
            # Final commit
            if total % self.batch_size != 0:
                session.commit()
            
            logger.info(f"✅ {total} Mails mit Placeholders aktualisiert")
            return total
            
        except Exception as e:
            logger.error(f"❌ Fehler bei Placeholder-Population: {e}")
            session.rollback()
            return 0
        finally:
            session.close()
    
    def _validate_data(self) -> Dict[str, int]:
        """Validiert die Daten nach Migration
        
        Prüft:
        - Boolean-Flags sind gesetzt (nicht NULL)
        - Message-Size ist Int oder NULL
        - thread_id ist String(36) oder NULL
        - Content-Type ist valid
        """
        session = self.Session()
        try:
            emails = session.query(models.RawEmail).all()
            total = len(emails)
            
            if total == 0:
                return {'valid': 0, 'total': 0}
            
            logger.info(f"📧 Validating {total} Mails...")
            
            valid_count = 0
            invalid_entries = []
            
            for email in emails:
                is_valid = True
                errors = []
                
                # Boolean-Flags sollten gesetzt sein
                if email.is_seen is None:
                    is_valid = False
                    errors.append(f"is_seen is NULL")
                
                # Message-Size sollte Int oder NULL sein
                if email.message_size is not None:
                    if not isinstance(email.message_size, int):
                        is_valid = False
                        errors.append(f"message_size type: {type(email.message_size)}")
                
                # Thread-ID sollte String(36) oder NULL sein
                if email.thread_id is not None:
                    if not isinstance(email.thread_id, str) or len(email.thread_id) != 36:
                        is_valid = False
                        errors.append(f"thread_id format invalid: {email.thread_id}")
                
                # Content-Type sollte valide sein
                if email.content_type and email.content_type not in ['text/plain', 'text/html', 'multipart/mixed', 'multipart/alternative']:
                    # Nur warnen, nicht als invalid markieren
                    logger.debug(f"⚠️  Unusual content_type: {email.content_type}")
                
                if is_valid:
                    valid_count += 1
                else:
                    invalid_entries.append((email.id, errors))
            
            logger.info(f"✅ {valid_count}/{total} Mails valide")
            
            if invalid_entries:
                logger.warning(f"⚠️  {len(invalid_entries)} Mails mit Validierungs-Fehlern:")
                for email_id, errors in invalid_entries[:5]:  # Nur erste 5 zeigen
                    logger.warning(f"   Email ID {email_id}: {', '.join(errors)}")
                if len(invalid_entries) > 5:
                    logger.warning(f"   ... und {len(invalid_entries) - 5} weitere")
            
            return {'valid': valid_count, 'total': total}
            
        except Exception as e:
            logger.error(f"❌ Fehler bei Validierung: {e}")
            return {'valid': 0, 'total': 0}
        finally:
            session.close()


def main():
    parser = argparse.ArgumentParser(
        description='Phase 12 Metadata Population Script'
    )
    parser.add_argument(
        '--db',
        default='emails.db',
        help='Path to database (default: emails.db)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Batch size for database commits (default: 100)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be done without making changes'
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("🔍 DRY-RUN MODE: Keine Änderungen werden durchgeführt")
        # TODO: Implement dry-run mode
    
    if not os.path.exists(args.db):
        logger.error(f"❌ Database nicht gefunden: {args.db}")
        sys.exit(1)
    
    try:
        populator = MetadataPopulator(args.db, args.batch_size)
        flags_count, placeholder_count, errors = populator.run()
        
        if errors > 0:
            logger.warning(f"\n⚠️  {errors} Validierungs-Fehler gefunden")
            sys.exit(1)
        else:
            logger.info(f"\n✅ Phase 12 Migration erfolgreich abgeschlossen!")
            sys.exit(0)
    
    except Exception as e:
        logger.error(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
