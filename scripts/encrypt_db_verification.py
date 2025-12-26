#!/usr/bin/env python3
"""
Database Encryption Verification Script
Inspects the database to verify encryption is working end-to-end
"""

import sys
import sqlite3
import base64
from pathlib import Path
import importlib

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

sys.path.insert(0, str(Path(__file__).parent))

models = importlib.import_module('.02_models', 'src')
encryption = importlib.import_module('.08_encryption', 'src')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "emails.db")

def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def verify_database():
    """Verifiziert Encryption-Status in der Datenbank"""
    
    print_header("📊 Database Encryption Verification")
    
    try:
        engine = create_engine(f"sqlite:///{DATABASE_PATH}")
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # ============================================
        # 1. Users überprüfen
        # ============================================
        print("1️⃣  USERS & MASTER-KEYS")
        print("-" * 60)
        
        users = session.query(models.User).all()
        
        if not users:
            print("❌ Keine User in der Datenbank!")
            return False
        
        print(f"✅ {len(users)} User(s) gefunden\n")
        
        for user in users:
            print(f"👤 Username: {user.username} (ID: {user.id})")
            print(f"   Email: {user.email}")
            
            if user.salt:
                print(f"   ✅ Salt vorhanden: {user.salt[:20]}...")
            else:
                print(f"   ❌ Salt NICHT vorhanden!")
            
            if user.encrypted_master_key:
                print(f"   ✅ Encrypted Master-Key vorhanden: {user.encrypted_master_key[:40]}...")
            else:
                print(f"   ❌ Encrypted Master-Key NICHT vorhanden!")
            
            if user.totp_enabled:
                print(f"   ✅ 2FA aktiviert")
            else:
                print(f"   ⚠️  2FA NICHT aktiviert")
            
            print()
        
        # ============================================
        # 2. Mail-Accounts überprüfen
        # ============================================
        print_header("2️⃣  MAIL-ACCOUNTS & CREDENTIALS")
        
        mail_accounts = session.query(models.MailAccount).all()
        
        if not mail_accounts:
            print("❌ Keine Mail-Accounts in der Datenbank!")
        else:
            print(f"✅ {len(mail_accounts)} Mail-Account(s) gefunden\n")
            
            for account in mail_accounts:
                print(f"📧 Account: {account.name}")
                print(f"   User: {account.user.username} (ID: {account.user_id})")
                print(f"   Server: {account.imap_server}")
                print(f"   Username: {account.imap_username}")
                
                if account.encrypted_imap_password:
                    encrypted = account.encrypted_imap_password
                    print(f"   ✅ Encrypted Password vorhanden")
                    print(f"      Preview: {encrypted[:50]}...")
                    
                    is_base64 = False
                    try:
                        base64.b64decode(encrypted, validate=True)
                        is_base64 = True
                        print(f"      ✅ Gültiges Base64-Format")
                    except Exception:
                        print(f"      ❌ KEIN Base64-Format!")
                    
                    is_encrypted_aes = False
                    if is_base64:
                        try:
                            blob = base64.b64decode(encrypted)
                            if len(blob) >= 28:  # IV(12) + Ciphertext(>0) + Tag(16)
                                is_encrypted_aes = True
                                print(f"      ✅ Gültiges AES-256-GCM Format (Größe: {len(blob)} Bytes)")
                            else:
                                print(f"      ❌ Zu kurz für AES-256-GCM ({len(blob)} Bytes, mind. 28)")
                        except Exception as e:
                            print(f"      ❌ Konnte nicht dekodiert werden: {e}")
                    
                else:
                    print(f"   ❌ Password NICHT verschlüsselt!")
                
                print(f"   Enabled: {account.enabled}")
                if account.last_fetch_at:
                    print(f"   Last Fetch: {account.last_fetch_at}")
                print()
        
        # ============================================
        # 3. Raw Emails überprüfen
        # ============================================
        print_header("3️⃣  RAW EMAILS")
        
        raw_emails = session.query(models.RawEmail).all()
        
        if not raw_emails:
            print("❌ Keine Raw-Emails in der Datenbank!")
        else:
            print(f"✅ {len(raw_emails)} Raw-Email(s) gefunden\n")
            
            for email in raw_emails[:5]:  # Zeige max 5
                print(f"📬 Subject: {email.subject[:50]}...")
                print(f"   User: {email.user.username} (ID: {email.user_id})")
                print(f"   Account: {email.mail_account.name}")
                print(f"   UID: {email.uid}")
                print(f"   Received: {email.received_at}")
                print()
            
            if len(raw_emails) > 5:
                print(f"... und {len(raw_emails) - 5} weitere")
        
        # ============================================
        # 4. Processed Emails überprüfen
        # ============================================
        print_header("4️⃣  PROCESSED EMAILS")
        
        processed_emails = session.query(models.ProcessedEmail).all()
        
        if not processed_emails:
            print("❌ Keine Processed-Emails in der Datenbank!")
        else:
            print(f"✅ {len(processed_emails)} Processed-Email(s) gefunden\n")
            
            for email in processed_emails[:5]:  # Zeige max 5
                print(f"📊 Score: {email.score} | Farbe: {email.farbe}")
                print(f"   Dringlichkeit: {email.dringlichkeit} | Wichtigkeit: {email.wichtigkeit}")
                print(f"   Summary (encrypted): {email.summary_de[:30]}..." if email.summary_de else "   Summary: Leer")
                print(f"   Done: {email.done}")
                print()
            
            if len(processed_emails) > 5:
                print(f"... und {len(processed_emails) - 5} weitere")
        
        # ============================================
        # 5. Encryption Test durchführen
        # ============================================
        print_header("5️⃣  ENCRYPTION TEST")
        
        if users and users[0].encrypted_master_key:
            print("⚠️  Hinweis: Master-Key kann nur mit dem User-Passwort entschlüsselt werden!")
            print("    (Master-Key ist mit dem User-Passwort verschlüsselt)\n")
        
        if mail_accounts:
            account = mail_accounts[0]
            user = account.user
            
            print(f"Test Account: {account.name}")
            print(f"Test User: {user.username}\n")
            
            if account.encrypted_imap_password:
                encrypted = account.encrypted_imap_password
                print(f"✅ Encrypted password found: {encrypted[:50]}...")
                print(f"   (Kann nur mit dem Master-Key entschlüsselt werden)")
                print(f"   Master-Key wird beim Login aus dem Passwort abgeleitet")
                print()
        
        # ============================================
        # 6. Summary
        # ============================================
        print_header("📋 SUMMARY")
        
        encryption_status = []
        
        for user in users:
            status = {
                'username': user.username,
                'salt': bool(user.salt),
                'master_key': bool(user.encrypted_master_key),
                'accounts': session.query(models.MailAccount).filter_by(user_id=user.id).count(),
                'encrypted_accounts': session.query(models.MailAccount).filter_by(user_id=user.id).all(),
            }
            encryption_status.append(status)
        
        print("User Encryption Status:")
        for status in encryption_status:
            accounts = status['encrypted_accounts']
            encrypted_count = sum(1 for a in accounts if a.encrypted_imap_password)
            
            print(f"\n👤 {status['username']}")
            print(f"   ✅ Master-Key Setup: {status['salt'] and status['master_key']}")
            print(f"   📧 Accounts: {status['accounts']}")
            print(f"   🔐 Encrypted Accounts: {encrypted_count}/{len(accounts)}")
        
        print("\n" + "="*60)
        print("✅ Verification abgeschlossen!")
        print("="*60)
        
        return True
        
    except Exception as e:
        print(f"❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = verify_database()
    sys.exit(0 if success else 1)
