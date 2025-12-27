#!/usr/bin/env python3
"""Migration: encrypted_master_key → encrypted_dek (Phase 8: DEK/KEK Pattern)

Für bestehende User:
1. Lädt encrypted_master_key aus DB
2. Entschlüsselt mit User-Passwort (ergibt alten Master-Key)
3. Verwendet alten Master-Key als DEK
4. Leitet KEK aus Passwort ab (PBKDF2)
5. Verschlüsselt DEK mit KEK
6. Speichert encrypted_dek in DB

ACHTUNG: Passwort-Input erforderlich!
"""

import logging
import getpass
import sys
import os

# Path-Fix für Import aus scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src import models, encryption

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_user_to_dek_kek(user, password: str, session) -> bool:
    """Migriert einen User von encrypted_master_key zu encrypted_dek
    
    Args:
        user: User-Model mit encrypted_master_key
        password: User-Passwort (für Entschlüsselung)
        session: SQLAlchemy Session
        
    Returns:
        True wenn erfolgreich, False bei Fehler
    """
    try:
        if not user.encrypted_master_key:
            logger.error(f"❌ User {user.id} hat kein encrypted_master_key")
            return False
        
        if user.encrypted_dek:
            logger.warning(f"⚠️ User {user.id} hat bereits encrypted_dek (überspringe)")
            return True
        
        # 1. Entschlüssle alten Master-Key
        logger.info(f"🔓 Entschlüssele Master-Key für User {user.id}...")
        old_master_key = encryption.EncryptionManager.decrypt_master_key(
            user.encrypted_master_key,
            password
        )
        
        if not old_master_key:
            logger.error(f"❌ Master-Key-Entschlüsselung fehlgeschlagen (falsches Passwort?)")
            return False
        
        logger.info("✅ Master-Key erfolgreich entschlüsselt")
        
        # 2. Verwende alten Master-Key als DEK
        dek = old_master_key
        
        # 3. Prüfe ob salt existiert (Legacy-User ohne salt)
        if not user.salt:
            logger.warning(f"⚠️ User {user.id} hat kein salt - generiere neues salt")
            user.salt = encryption.EncryptionManager.generate_salt()
            session.commit()
        
        # 4. Leite KEK aus Passwort ab
        logger.info("🔑 Leite KEK aus Passwort ab...")
        kek = encryption.EncryptionManager.generate_master_key(password, user.salt)
        
        # 5. Verschlüssle DEK mit KEK
        logger.info("🔐 Verschlüssle DEK mit KEK...")
        encrypted_dek = encryption.EncryptionManager.encrypt_dek(dek, kek)
        
        # 6. Speichere encrypted_dek
        user.encrypted_dek = encrypted_dek
        session.commit()
        
        logger.info(f"✅ User {user.id} erfolgreich migriert (encrypted_dek gespeichert)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration fehlgeschlagen: {e}")
        session.rollback()
        return False


def main():
    """Hauptfunktion: Migriert alle User mit encrypted_master_key"""
    
    # DB-Verbindung
    db_path = os.path.join(os.path.dirname(__file__), "..", "emails.db")
    _, SessionFactory = models.init_db(db_path)
    session = SessionFactory()
    
    try:
        # Finde alle User mit encrypted_master_key aber ohne encrypted_dek
        users = session.query(models.User).filter(
            models.User.encrypted_master_key.isnot(None),
            models.User.encrypted_dek.is_(None)
        ).all()
        
        if not users:
            logger.info("✅ Keine User zur Migration gefunden (alle bereits migriert)")
            return 0
        
        logger.info(f"📊 {len(users)} User zur Migration gefunden:")
        for user in users:
            logger.info(f"  - User {user.id}: {user.username} ({user.email})")
        
        print("\n" + "="*70)
        print("⚠️  ACHTUNG: Migration encrypted_master_key → encrypted_dek")
        print("="*70)
        print("Diese Migration:")
        print("1. Entschlüsselt den alten Master-Key mit deinem Passwort")
        print("2. Verwendet ihn als DEK (Data Encryption Key)")
        print("3. Verschlüsselt DEK mit KEK (Key Encryption Key aus Passwort)")
        print()
        print("✅ Deine E-Mails bleiben verschlüsselt und lesbar")
        print("✅ Nach Migration kannst du Passwort ändern ohne E-Mails neu zu verschlüsseln")
        print()
        
        # User-Bestätigung
        confirm = input("Migration starten? (ja/nein): ").strip().lower()
        if confirm not in ['ja', 'j', 'yes', 'y']:
            logger.info("❌ Migration abgebrochen")
            return 1
        
        # Migriere User einzeln
        success_count = 0
        for user in users:
            print(f"\n{'='*70}")
            print(f"🔄 Migriere User: {user.username}")
            print(f"{'='*70}")
            
            # Passwort-Eingabe
            password = getpass.getpass(f"Passwort für {user.username}: ")
            
            if migrate_user_to_dek_kek(user, password, session):
                success_count += 1
                print(f"✅ Migration erfolgreich für {user.username}")
            else:
                print(f"❌ Migration fehlgeschlagen für {user.username}")
                retry = input("Erneut versuchen? (ja/nein): ").strip().lower()
                if retry in ['ja', 'j', 'yes', 'y']:
                    password = getpass.getpass(f"Passwort für {user.username}: ")
                    if migrate_user_to_dek_kek(user, password, session):
                        success_count += 1
                        print(f"✅ Migration erfolgreich für {user.username}")
        
        print(f"\n{'='*70}")
        print(f"📊 Migration abgeschlossen: {success_count}/{len(users)} erfolgreich")
        print(f"{'='*70}")
        
        return 0 if success_count == len(users) else 1
        
    except Exception as e:
        logger.error(f"❌ Unerwarteter Fehler: {e}")
        return 1
        
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
