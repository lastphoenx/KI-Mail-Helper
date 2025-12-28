#!/usr/bin/env python3
"""
Testdaten-Setup für CLI/Cron-Job Tests
Erstellt einen Test-User mit verschlüsseltem Mail-Account
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import importlib
models = importlib.import_module('.02_models', 'src')
auth = importlib.import_module('.07_auth', 'src')
encryption = importlib.import_module('.08_encryption', 'src')

from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH = "emails.db"

def setup_test_data():
    """Erstellt Test-Daten für CLI-Tests"""
    
    print("📊 Initialisiere Datenbank...")
    engine, Session = models.init_db(DATABASE_PATH)
    session = Session()
    
    try:
        existing_user = session.query(models.User).filter_by(username="testuser").first()
        if existing_user:
            print("⚠️  Test-User existiert bereits. Überspringe Setup.")
            return existing_user.id
        
        print("👤 Erstelle Test-User: testuser")
        user = models.User(
            username="testuser",
            email="testuser@local.test"
        )
        user.set_password("testpass123")
        session.add(user)
        session.flush()
        
        print("🔐 Erstelle Master-Keys...")
        salt, encrypted_master_key = auth.MasterKeyManager.setup_master_key_for_user(
            user.id, 
            "testpass123",
            session
        )
        
        print("📧 Erstelle Test Mail-Account...")
        # Test-Passwort: Dummy für Testdaten (nicht produktiv!)
        # In Tests wird die Verschlüsselung getestet, nicht die IMAP-Verbindung
        test_password = "DUMMY-TEST-PASSWORD-NOT-FOR-PRODUCTION"
        master_key = encryption.EncryptionManager.generate_master_key("testpass123", salt)
        encrypted_imap_password = encryption.CredentialManager.encrypt_imap_password(
            test_password,
            master_key
        )
        
        mail_account = models.MailAccount(
            user_id=user.id,
            name="Test Gmail",
            imap_server="imap.gmail.com",
            imap_username="testuser@gmail.com",
            encrypted_imap_password=encrypted_imap_password,
            enabled=True
        )
        session.add(mail_account)
        session.commit()
        
        print(f"""
✅ Test-Daten erstellt!

📝 Testdaten:
   Username: testuser
   Password: testpass123
   Email: testuser@local.test
   
📧 Mail-Account:
   Name: Test Gmail
   Server: imap.gmail.com
   IMAP-User: testuser@gmail.com
   IMAP-Pass: (verschlüsselt mit Master-Key)
   
🔐 Master-Key Info:
   Benutzer-ID: {user.id}
   Salt: {salt[:20]}...
   Encrypted Master-Key: {encrypted_master_key[:20]}...

🚀 Nächste Schritte:

1. Web-UI testen (sollte schon laufen):
   http://0.0.0.0:5000
   Login: testuser / testpass123

2. CLI-Test mit --process-once:
   export SERVER_MASTER_SECRET="{os.getenv('SERVER_MASTER_SECRET')}"
   python -m src.00_main --process-once

3. Der CLI-Test wird:
   ✓ Master-Key mit SERVER_MASTER_SECRET laden
   ✓ IMAP-Passwort entschlüsseln
   ✓ Verbindung zu Gmail versuchen (wird fehlschlagen ohne real credentials)
   ✓ Zeigt, dass Entschlüsselung funktioniert!
        """)
        
        return user.id
        
    except Exception as e:
        print(f"❌ Fehler beim Setup: {e}")
        session.rollback()
        return None
    finally:
        session.close()

if __name__ == "__main__":
    setup_test_data()
