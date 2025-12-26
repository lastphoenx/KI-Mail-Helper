#!/usr/bin/env python3
"""
Test-Skript für IMAP und Google OAuth Mail Fetcher
Testet beide Flows und deren Error Handling
"""

import sys
import os
import importlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

models = importlib.import_module('src.02_models')
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_imap_connection():
    """Testet IMAP-Verbindung"""
    print("\n" + "="*60)
    print("🧪 TEST 1: IMAP Mail Fetcher")
    print("="*60)
    
    mail_fetcher = importlib.import_module('src.06_mail_fetcher')
    
    try:
        server = os.getenv('TEST_IMAP_SERVER')
        username = os.getenv('TEST_IMAP_USERNAME')
        password = os.getenv('TEST_IMAP_PASSWORD')
        port = int(os.getenv('TEST_IMAP_PORT', '993'))
        
        if not all([server, username, password]):
            print("⏭️  IMAP-Test übersprungen (Umgebungsvariablen nicht gesetzt)")
            print("   Setze diese für Test: TEST_IMAP_SERVER, TEST_IMAP_USERNAME, TEST_IMAP_PASSWORD")
            return True
        
        print(f"📧 Verbinde zu {server}:{port}")
        fetcher = mail_fetcher.MailFetcher(server, username, password, port)
        fetcher.connect()
        
        print("✅ Verbindung erfolgreich")
        
        print("📬 Hole neue Mails...")
        emails = fetcher.fetch_new_emails(limit=5)
        
        print(f"✅ {len(emails)} Mails abgerufen")
        
        for email in emails[:2]:
            print(f"\n  Von: {email['sender']}")
            print(f"  Betreff: {email['subject']}")
            print(f"  Body-Länge: {len(email['body'])} Zeichen")
        
        fetcher.disconnect()
        print("✅ IMAP-Test bestanden!")
        return True
        
    except Exception as e:
        print(f"❌ IMAP-Test fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_google_oauth():
    """Testet Google OAuth Mock"""
    print("\n" + "="*60)
    print("🧪 TEST 2: Google OAuth Manager")
    print("="*60)
    
    google_oauth = importlib.import_module('src.10_google_oauth')
    
    try:
        client_id = "test-client-id.apps.googleusercontent.com"
        redirect_uri = "http://localhost:5000/settings/mail-account/google/callback"
        
        print("📝 Generiere Auth URL...")
        auth_url = google_oauth.GoogleOAuthManager.get_auth_url(client_id, redirect_uri)
        
        if "accounts.google.com" in auth_url and "scope" in auth_url:
            print("✅ Auth URL generiert:")
            print(f"   {auth_url[:80]}...")
        else:
            print("❌ Auth URL ungültig")
            return False
        
        print("\n✅ Google OAuth Manager funktioniert!")
        return True
        
    except Exception as e:
        print(f"❌ Google OAuth Test fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_encryption():
    """Testet Encryption von Credentials"""
    print("\n" + "="*60)
    print("🧪 TEST 3: Credential Encryption")
    print("="*60)
    
    encryption = importlib.import_module('src.08_encryption')
    
    try:
        password = "test-password-12345"
        salt = encryption.EncryptionManager.generate_salt()
        master_key = encryption.EncryptionManager.generate_master_key(password, salt)
        
        print("🔐 Generiere Master-Key...")
        print(f"   Salt: {salt[:20]}...")
        print(f"   Master-Key: {master_key[:20]}...")
        
        imap_password = "my-secret-imap-password"
        encrypted = encryption.CredentialManager.encrypt_imap_password(imap_password, master_key)
        
        print("\n🔒 Verschlüssele IMAP-Passwort...")
        print(f"   Original: {imap_password}")
        print(f"   Encrypted: {encrypted[:20]}...")
        
        decrypted = encryption.CredentialManager.decrypt_imap_password(encrypted, master_key)
        
        print("\n🔓 Entschlüssele IMAP-Passwort...")
        print(f"   Decrypted: {decrypted}")
        
        if decrypted == imap_password:
            print("✅ Encryption Test bestanden!")
            return True
        else:
            print("❌ Decryption Match fehlgeschlagen")
            return False
        
    except Exception as e:
        print(f"❌ Encryption Test fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database():
    """Testet Database Models"""
    print("\n" + "="*60)
    print("🧪 TEST 4: Database Models")
    print("="*60)
    
    try:
        db_path = "emails.db"
        
        if not os.path.exists(db_path):
            print(f"⏭️  Database-Test übersprungen ({db_path} nicht gefunden)")
            return True
        
        engine = create_engine(f"sqlite:///{db_path}")
        Session = sessionmaker(bind=engine)
        db = Session()
        
        print("📊 Überprüfe Database-Struktur...")
        
        users = db.query(models.User).count()
        accounts = db.query(models.MailAccount).count()
        
        print(f"   Users in DB: {users}")
        print(f"   Mail Accounts in DB: {accounts}")
        
        if accounts > 0:
            account = db.query(models.MailAccount).first()
            print(f"\n   Beispiel Account:")
            print(f"   - Name: {account.name}")
            print(f"   - Provider: {account.oauth_provider or 'IMAP'}")
            print(f"   - Server: {account.imap_server}")
            print(f"   - OAuth Token vorhanden: {bool(account.encrypted_oauth_token)}")
        
        db.close()
        print("✅ Database Test bestanden!")
        return True
        
    except Exception as e:
        print(f"❌ Database Test fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "🚀"*30)
    print("Mail Helper - Test Suite für IMAP & OAuth")
    print("🚀"*30)
    
    results = {
        "IMAP": test_imap_connection(),
        "Google OAuth": test_google_oauth(),
        "Encryption": test_encryption(),
        "Database": test_database()
    }
    
    print("\n" + "="*60)
    print("📋 SUMMARY")
    print("="*60)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:<20} {status}")
    
    total = len(results)
    passed = sum(results.values())
    
    print(f"\n{passed}/{total} Tests bestanden")
    
    if passed == total:
        print("🎉 Alle Tests erfolgreich!")
        return 0
    else:
        print(f"⚠️  {total - passed} Test(s) fehlgeschlagen")
        return 1


if __name__ == "__main__":
    sys.exit(main())
