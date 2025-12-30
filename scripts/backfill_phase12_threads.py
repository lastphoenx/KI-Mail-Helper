#!/usr/bin/env python3
"""
Backfill Script für Phase 12: Thread-Metadaten
==============================================
Verarbeitet bestehende RawEmails ohne thread_id und berechnet:
- thread_id (UUID für Thread-Gruppierung)
- parent_uid (IMAP-UID des Elternelements)

Nutzt ThreadCalculator.from_message_id_chain() für In-Reply-To/References.

Verwendung:
    python3 scripts/backfill_phase12_threads.py --master-key <key>

Optionen:
    --batch-size N  Verarbeite N Emails pro Commit (Standard: 100)
    --dry-run       Zeige Änderungen ohne sie zu speichern
"""
import sys
import argparse
import logging
from pathlib import Path

# Pfad-Setup für Imports
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import importlib
models = importlib.import_module('src.02_models')
mail_fetcher = importlib.import_module('src.06_mail_fetcher')
ThreadCalculator = mail_fetcher.ThreadCalculator
encryption = importlib.import_module('src.08_encryption')
EncryptionManager = encryption.EncryptionManager
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(project_root / "logs" / "backfill_threads.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def backfill_threads(db_path: str, master_key: str, batch_size: int = 100, dry_run: bool = False):
    """
    Hauptfunktion für Thread-Backfill.

    Args:
        db_path: Pfad zur SQLite-Datenbank
        master_key: Master-Key für Entschlüsselung
        batch_size: Anzahl Emails pro Batch-Commit
        dry_run: Wenn True, keine Änderungen speichern
    """
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Finde alle RawEmails ohne thread_id
        stmt = select(models.RawEmail).where(
            models.RawEmail.thread_id.is_(None)
        ).order_by(models.RawEmail.mail_account_id, models.RawEmail.folder, models.RawEmail.date_received)
        
        emails_to_update = session.execute(stmt).scalars().all()
        total = len(emails_to_update)
        
        if total == 0:
            logger.info("✅ Keine RawEmails ohne thread_id gefunden. Backfill nicht nötig.")
            return

        logger.info(f"📧 Gefunden: {total} RawEmails ohne thread_id")
        
        # Gruppiere nach Account + Folder für korrekten UID-Kontext
        grouped = {}
        for email in emails_to_update:
            key = (email.mail_account_id, email.imap_folder)  # WARN-001-FIX: imap_folder nicht folder
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(email)

        logger.info(f"📁 Verteilt auf {len(grouped)} Account/Folder-Kombinationen")

        updated_count = 0
        skipped_count = 0

        for (account_id, folder), emails in grouped.items():
            logger.info(f"🔄 Verarbeite Account {account_id} / Folder '{folder}': {len(emails)} Emails")

            # Entschlüssele In-Reply-To/References für ThreadCalculator
            decrypted_data = {}
            for email in emails:
                try:
                    in_reply_to = None
                    references = None

                    if email.encrypted_in_reply_to:
                        in_reply_to = EncryptionManager.decrypt_data(email.encrypted_in_reply_to, master_key)
                    
                    if email.encrypted_references:
                        references = EncryptionManager.decrypt_data(email.encrypted_references, master_key)

                    decrypted_data[email.imap_uid] = {
                        "message_id": email.message_id,
                        "in_reply_to": in_reply_to,
                        "references": references,
                    }
                except Exception as e:
                    logger.warning(f"⚠️  Entschlüsselung fehlgeschlagen für UID {email.imap_uid}: {e}")
                    skipped_count += 1
                    continue

            # Berechne Threads für diese Gruppe
            # ISSUE-001-FIX: ThreadCalculator erwartet emails Dict, nicht einzelne Parameter
            thread_ids, parent_uids = ThreadCalculator.from_message_id_chain(decrypted_data)
            
            for email in emails:
                if email.imap_uid not in decrypted_data:
                    continue  # Wurde übersprungen wegen Entschlüsselungsfehler
                
                try:
                    # Update Felder aus berechneten Thread-IDs
                    email.thread_id = thread_ids.get(email.imap_uid)
                    email.parent_uid = parent_uids.get(email.imap_uid)

                    updated_count += 1

                    # Batch-Commit
                    if updated_count % batch_size == 0:
                        if not dry_run:
                            session.commit()
                            logger.info(f"💾 Batch-Commit: {updated_count}/{total} aktualisiert")
                        else:
                            logger.info(f"🔍 DRY-RUN: Würde {updated_count}/{total} committen")

                except Exception as e:
                    logger.error(f"❌ Thread-Berechnung fehlgeschlagen für UID {email.imap_uid}: {e}")
                    skipped_count += 1

        # Final Commit
        if not dry_run and updated_count % batch_size != 0:
            session.commit()

        logger.info("✅ Backfill abgeschlossen:")
        logger.info(f"   - Aktualisiert: {updated_count}")
        logger.info(f"   - Übersprungen: {skipped_count}")
        if dry_run:
            logger.info("   - DRY-RUN: Keine Änderungen gespeichert")

    except Exception as e:
        logger.error(f"❌ Fehler beim Backfill: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Backfill Thread-Metadaten für bestehende RawEmails"
    )
    parser.add_argument(
        "--master-key",
        required=True,
        help="Master-Key für Entschlüsselung (hex-kodiert)",
    )
    parser.add_argument(
        "--db-path",
        default=str(project_root / "emails.db"),
        help="Pfad zur SQLite-Datenbank (Standard: emails.db)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Anzahl Emails pro Batch-Commit (Standard: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Zeige Änderungen ohne sie zu speichern",
    )

    args = parser.parse_args()

    logger.info("🚀 Starte Phase 12 Thread-Backfill")
    logger.info(f"   - Datenbank: {args.db_path}")
    logger.info(f"   - Batch-Size: {args.batch_size}")
    logger.info(f"   - Dry-Run: {args.dry_run}")

    backfill_threads(
        db_path=args.db_path,
        master_key=args.master_key,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
