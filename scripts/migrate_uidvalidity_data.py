#!/usr/bin/env python3
"""
UIDVALIDITY Data Migration Script (Phase 14a)

Dieses Script befüllt bestehende RawEmails mit UIDVALIDITY vom Server.

WAS ES TUT:
1. Findet alle RawEmails mit imap_uidvalidity = NULL
2. Gruppiert nach (user_id, mail_account_id, imap_folder)
3. Verbindet zu jedem IMAP Account
4. Fragt UIDVALIDITY für jeden Ordner ab (SELECT folder)
5. Updatet raw_emails.imap_uidvalidity
6. Speichert mail_accounts.folder_uidvalidity (JSON)

USAGE:
    python scripts/migrate_uidvalidity_data.py

VORAUSSETZUNGEN:
- Alembic Migration ph14a_rfc_unique_key_uidvalidity wurde ausgeführt
- User muss angemeldet sein (Master-Key wird benötigt)
- Oder: Master-Key als ENV-Variable setzen

HINWEIS:
- Das Script arbeitet Batch-weise (100 Accounts pro Durchlauf)
- Bei vielen Accounts: mehrfach ausführen
- Fehler werden geloggt aber stoppen nicht den gesamten Prozess
"""

import sys
import os
import logging
from datetime import datetime, UTC
from typing import Dict, List, Tuple, Optional
import getpass

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, create_engine
from sqlalchemy.orm import sessionmaker
from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError

# Import Models
from src import models_02 as models
from src import encryption_05 as encryption

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UIDValidityMigrator:
    """Migriert bestehende RawEmails zu UIDVALIDITY-Schema"""
    
    def __init__(self, session, master_key: str):
        self.session = session
        self.master_key = master_key
        self.stats = {
            'accounts_processed': 0,
            'accounts_failed': 0,
            'folders_processed': 0,
            'emails_updated': 0,
            'emails_failed': 0,
        }
    
    def run(self, limit: int = 100) -> Dict:
        """Führt Migration durch
        
        Args:
            limit: Max. Anzahl Accounts pro Durchlauf
            
        Returns:
            Statistik-Dict
        """
        logger.info("=" * 70)
        logger.info("UIDVALIDITY DATA MIGRATION - Phase 14a")
        logger.info("=" * 70)
        
        # 1. Accounts finden die Migration benötigen
        accounts_to_migrate = self._find_accounts_needing_migration(limit)
        
        if not accounts_to_migrate:
            logger.info("✅ Keine Accounts benötigen Migration (alle haben UIDVALIDITY)")
            return self.stats
        
        logger.info(f"📋 {len(accounts_to_migrate)} Accounts benötigen Migration")
        
        # 2. Für jeden Account: UIDVALIDITY vom Server holen
        for account in accounts_to_migrate:
            try:
                self._migrate_account(account)
                self.stats['accounts_processed'] += 1
            except Exception as e:
                logger.error(f"❌ Account {account.id} ({account.name}) fehlgeschlagen: {e}")
                self.stats['accounts_failed'] += 1
                continue
        
        # 3. Zusammenfassung
        logger.info("=" * 70)
        logger.info("MIGRATION ABGESCHLOSSEN")
        logger.info("=" * 70)
        logger.info(f"✅ Accounts migriert: {self.stats['accounts_processed']}")
        logger.info(f"❌ Accounts fehlgeschlagen: {self.stats['accounts_failed']}")
        logger.info(f"📁 Ordner verarbeitet: {self.stats['folders_processed']}")
        logger.info(f"📧 Emails aktualisiert: {self.stats['emails_updated']}")
        logger.info(f"⚠️  Emails fehlgeschlagen: {self.stats['emails_failed']}")
        
        return self.stats
    
    def _find_accounts_needing_migration(self, limit: int) -> List[models.MailAccount]:
        """Findet Accounts mit Emails ohne UIDVALIDITY"""
        
        # Subquery: Accounts mit NULL UIDVALIDITY Emails
        subq = (
            self.session.query(models.RawEmail.mail_account_id.distinct())
            .filter(models.RawEmail.imap_uidvalidity == None)
            .filter(models.RawEmail.deleted_at == None)
            .subquery()
        )
        
        # Accounts laden (nur IMAP, nur enabled)
        accounts = (
            self.session.query(models.MailAccount)
            .filter(models.MailAccount.id.in_(subq))
            .filter(models.MailAccount.auth_type == 'imap')
            .filter(models.MailAccount.enabled == True)
            .limit(limit)
            .all()
        )
        
        return accounts
    
    def _migrate_account(self, account: models.MailAccount) -> None:
        """Migriert einen Account (alle Ordner)"""
        
        logger.info(f"📬 Account {account.id}: {account.name}")
        
        # 1. IMAP Credentials entschlüsseln
        try:
            imap_server = encryption.CredentialManager.decrypt_server(
                account.encrypted_imap_server, self.master_key
            )
            imap_username = encryption.CredentialManager.decrypt_email_address(
                account.encrypted_imap_username, self.master_key
            )
            imap_password = encryption.CredentialManager.decrypt_imap_password(
                account.encrypted_imap_password, self.master_key
            )
        except Exception as e:
            logger.error(f"   ❌ Entschlüsselung fehlgeschlagen: {e}")
            raise
        
        # 2. IMAP Verbindung aufbauen
        client = None
        try:
            client = IMAPClient(
                host=imap_server,
                port=account.imap_port or 993,
                ssl=(account.imap_encryption == 'SSL'),
                timeout=30.0
            )
            client.login(imap_username, imap_password)
            logger.info(f"   ✅ IMAP verbunden: {imap_server}")
        except Exception as e:
            logger.error(f"   ❌ IMAP Verbindung fehlgeschlagen: {e}")
            raise
        
        try:
            # 3. Ordner finden die Migration brauchen
            folders = self._find_folders_needing_migration(account)
            
            if not folders:
                logger.info(f"   ℹ️  Keine Ordner benötigen Migration")
                return
            
            logger.info(f"   📁 {len(folders)} Ordner zu migrieren: {', '.join(folders)}")
            
            # 4. Für jeden Ordner: UIDVALIDITY abfragen
            folder_uidvalidities = {}
            
            for folder in folders:
                try:
                    # SELECT folder → gibt UIDVALIDITY zurück
                    folder_info = client.select_folder(folder, readonly=True)
                    uidvalidity_raw = folder_info.get(b'UIDVALIDITY')
                    
                    # UIDVALIDITY extrahieren (kann int oder [int] sein)
                    if uidvalidity_raw:
                        if isinstance(uidvalidity_raw, list):
                            uidvalidity = int(uidvalidity_raw[0])
                        else:
                            uidvalidity = int(uidvalidity_raw)
                        
                        folder_uidvalidities[folder] = uidvalidity
                        logger.info(f"      ✓ {folder}: UIDVALIDITY={uidvalidity}")
                        self.stats['folders_processed'] += 1
                    else:
                        logger.warning(f"      ⚠️  {folder}: Keine UIDVALIDITY vom Server")
                        
                except Exception as e:
                    logger.error(f"      ❌ {folder}: {e}")
                    continue
            
            # 5. DB updaten
            if folder_uidvalidities:
                updated = self._update_emails_with_uidvalidity(
                    account, folder_uidvalidities
                )
                logger.info(f"   ✅ {updated} Emails mit UIDVALIDITY aktualisiert")
                
                # 6. MailAccount.folder_uidvalidity speichern
                for folder, uidvalidity in folder_uidvalidities.items():
                    account.set_uidvalidity(folder, uidvalidity)
                
                self.session.commit()
                logger.info(f"   💾 Account UIDVALIDITY gespeichert")
            
        finally:
            if client:
                try:
                    client.logout()
                except:
                    pass
    
    def _find_folders_needing_migration(
        self, account: models.MailAccount
    ) -> List[str]:
        """Findet Ordner mit Emails ohne UIDVALIDITY"""
        
        result = (
            self.session.query(models.RawEmail.imap_folder.distinct())
            .filter(models.RawEmail.mail_account_id == account.id)
            .filter(models.RawEmail.imap_uidvalidity == None)
            .filter(models.RawEmail.deleted_at == None)
            .all()
        )
        
        return [folder for (folder,) in result if folder]
    
    def _update_emails_with_uidvalidity(
        self, 
        account: models.MailAccount,
        folder_uidvalidities: Dict[str, int]
    ) -> int:
        """Updatet RawEmails mit UIDVALIDITY
        
        Returns:
            Anzahl aktualisierte Emails
        """
        total_updated = 0
        
        for folder, uidvalidity in folder_uidvalidities.items():
            try:
                updated = (
                    self.session.query(models.RawEmail)
                    .filter(models.RawEmail.mail_account_id == account.id)
                    .filter(models.RawEmail.imap_folder == folder)
                    .filter(models.RawEmail.imap_uidvalidity == None)
                    .filter(models.RawEmail.deleted_at == None)
                    .update({
                        'imap_uidvalidity': uidvalidity
                    })
                )
                
                total_updated += updated
                self.stats['emails_updated'] += updated
                
            except Exception as e:
                logger.error(f"      ❌ Update fehlgeschlagen für {folder}: {e}")
                self.stats['emails_failed'] += updated
                raise
        
        return total_updated


def main():
    """Main entry point"""
    
    print("""
╔═══════════════════════════════════════════════════════════════╗
║  UIDVALIDITY DATA MIGRATION - Phase 14a                       ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  Dieses Script befüllt bestehende RawEmails mit UIDVALIDITY. ║
║                                                               ║
║  ⚠️  WICHTIG:                                                  ║
║  - Alembic Migration muss ausgeführt sein                     ║
║  - Master-Key wird benötigt                                   ║
║  - Script kann mehrfach ausgeführt werden                     ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # 1. Database Connection
    db_path = os.path.join(os.path.dirname(__file__), '..', 'emails.db')
    engine = create_engine(f'sqlite:///{db_path}')
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # 2. Master-Key abfragen
        master_key = os.environ.get('MASTER_KEY')
        
        if not master_key:
            print("\n🔐 Master-Key eingeben (wird nicht angezeigt):")
            master_key = getpass.getpass("Master-Key: ")
        
        if not master_key:
            print("❌ Master-Key benötigt!")
            sys.exit(1)
        
        # 3. Migration ausführen
        migrator = UIDValidityMigrator(session, master_key)
        stats = migrator.run(limit=100)
        
        # 4. Success
        if stats['accounts_failed'] == 0:
            print("\n✅ Migration erfolgreich!")
            sys.exit(0)
        else:
            print(f"\n⚠️  Migration teilweise erfolgreich ({stats['accounts_failed']} Fehler)")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration abgebrochen durch User")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Fataler Fehler: {e}", exc_info=True)
        sys.exit(1)
    finally:
        session.close()


if __name__ == '__main__':
    main()
