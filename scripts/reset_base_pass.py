#!/usr/bin/env python3
"""
Reset Base-Pass Analysis – Löscht alle ProcessedEmail-Einträge,
damit der Worker sämtliche RawEmails neu verarbeitet.

Verwendung:
  python3 scripts/reset_base_pass.py              # Alle Emails
  python3 scripts/reset_base_pass.py --account=1  # Nur Account ID 1
  python3 scripts/reset_base_pass.py --user=1     # Nur User ID 1
  python3 scripts/reset_base_pass.py --force      # Ohne Bestätigung

Vorsicht: Worker sollte während des Löschens NICHT laufen!
"""

import sys
import os
import importlib
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
models = importlib.import_module('.02_models', 'src')


def reset_base_pass(account_id=None, user_id=None, force=False):
    """Löscht ProcessedEmail-Einträge für Basis-Pass Neu-Lauf"""
    
    engine, Session = models.init_db("emails.db")
    session = Session()
    
    try:
        query = session.query(models.ProcessedEmail)
        
        scope_desc = "alle Emails"
        if account_id:
            query = query.join(models.RawEmail).filter(
                models.RawEmail.mail_account_id == account_id
            )
            scope_desc = f"Account ID {account_id}"
        elif user_id:
            query = query.join(models.RawEmail).filter(
                models.RawEmail.user_id == user_id
            )
            scope_desc = f"User ID {user_id}"
        
        count = query.count()
        
        if count == 0:
            print(f"ℹ️  Keine ProcessedEmails gefunden für {scope_desc}")
            return True
        
        print(f"⚠️  Werden gelöscht: {count} ProcessedEmail-Einträge ({scope_desc})")
        
        if not force:
            confirm = input("Fortfahren? [y/N]: ").strip().lower()
            if confirm != 'y':
                print("❌ Abgebrochen")
                return False
        
        deleted = query.delete(synchronize_session=False)
        session.commit()
        
        print(f"✅ {deleted} ProcessedEmail-Einträge gelöscht")
        print("📋 Worker wird diese RawEmails beim nächsten Run neu verarbeiten (Base-Pass)")
        return True
        
    except Exception as e:
        session.rollback()
        print(f"❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Lösche ProcessedEmails für Base-Pass Neu-Lauf",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python3 scripts/reset_base_pass.py              # Alle Emails löschen
  python3 scripts/reset_base_pass.py --account=1  # Nur Account 1
  python3 scripts/reset_base_pass.py --user=1     # Nur User 1
  python3 scripts/reset_base_pass.py --force      # Ohne Bestätigung
        """
    )
    parser.add_argument('--account', type=int, help='Nur für diese Mail-Account ID')
    parser.add_argument('--user', type=int, help='Nur für diese User ID')
    parser.add_argument('--force', action='store_true', help='Ohne Bestätigung löschen')
    
    args = parser.parse_args()
    
    print("🔄 Base-Pass Reset Tool")
    print("=" * 60)
    
    success = reset_base_pass(
        account_id=args.account,
        user_id=args.user,
        force=args.force
    )
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
