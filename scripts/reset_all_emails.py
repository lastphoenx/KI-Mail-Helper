#!/usr/bin/env python3
"""
Reset All Emails – Löscht alle RawEmails und ProcessedEmails,
damit beim nächsten Abrufen alles neu abgerufen und verarbeitet wird.

User-Account und Mail-Account-Daten bleiben erhalten!

Verwendung:
  python3 scripts/reset_all_emails.py              # Alle Emails
  python3 scripts/reset_all_emails.py --account=1  # Nur Account ID 1
  python3 scripts/reset_all_emails.py --user=1     # Nur User ID 1
  python3 scripts/reset_all_emails.py --force      # Ohne Bestätigung

Vorsicht: Worker sollte während des Löschens NICHT laufen!
"""

import sys
import os
import importlib
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
models = importlib.import_module('.02_models', 'src')


def reset_all_emails(account_id=None, user_id=None, force=False, hard_delete=False):
    """Löscht RawEmail UND ProcessedEmail Einträge für kompletten Neustart
    
    Args:
        hard_delete: If True, HARD DELETE (records gone forever)
                    If False, SOFT DELETE (deleted_at = NOW, keeps audit trail)
                    Default: False (soft-delete)
    """
    
    engine, Session = models.init_db("emails.db")
    session = Session()
    
    try:
        # Zuerst RawEmail IDs sammeln
        raw_query = session.query(models.RawEmail.id)
        
        scope_desc = "alle Emails"
        if account_id:
            raw_query = raw_query.filter(models.RawEmail.mail_account_id == account_id)
            scope_desc = f"Account ID {account_id}"
        elif user_id:
            raw_query = raw_query.filter(models.RawEmail.user_id == user_id)
            scope_desc = f"User ID {user_id}"
        
        raw_ids = [row[0] for row in raw_query.all()]
        
        if not raw_ids:
            print(f"ℹ️  Keine E-Mails gefunden für {scope_desc}")
            return True
        
        # ProcessedEmails zählen (die zu diesen RawEmails gehören)
        processed_count = session.query(models.ProcessedEmail).filter(
            models.ProcessedEmail.raw_email_id.in_(raw_ids)
        ).count()
        
        raw_count = len(raw_ids)
        total = processed_count + raw_count
        
        if total == 0:
            print(f"ℹ️  Keine E-Mails gefunden für {scope_desc}")
            return True
        
        print(f"⚠️  Werden gelöscht:")
        print(f"   📧 {raw_count} RawEmail-Einträge (abgerufene E-Mails)")
        print(f"   🤖 {processed_count} ProcessedEmail-Einträge (KI-Analysen)")
        print(f"   📊 Gesamt: {total} Einträge ({scope_desc})")
        print()
        print(f"✅ BLEIBT ERHALTEN:")
        print(f"   👤 User-Account")
        print(f"   📬 Mail-Account (IMAP/SMTP Zugangsdaten)")
        print(f"   ⚙️  Alle Einstellungen")
        print()
        
        if not force:
            confirm = input("🚨 Wirklich alle E-Mails löschen? [y/N]: ").strip().lower()
            if confirm != 'y':
                print("❌ Abgebrochen")
                return False
        
        # Erst ProcessedEmails löschen (wegen Foreign Key)
        if hard_delete:
            # HARD DELETE: Records komplett weg, keine UID-Konflikte beim Re-Fetch
            deleted_processed = session.query(models.ProcessedEmail).filter(
                models.ProcessedEmail.raw_email_id.in_(raw_ids)
            ).delete(synchronize_session=False)
        else:
            # SOFT DELETE: deleted_at = NOW, Audit-Trail bleibt erhalten
            from datetime import datetime, UTC
            deleted_processed = session.query(models.ProcessedEmail).filter(
                models.ProcessedEmail.raw_email_id.in_(raw_ids)
            ).update(
                {"deleted_at": datetime.now(UTC)},
                synchronize_session=False
            )
        session.flush()
        
        # Dann RawEmails löschen
        if hard_delete:
            # HARD DELETE: Sauberer Re-Fetch ohne UID-Konflikte
            deleted_raw = session.query(models.RawEmail).filter(
                models.RawEmail.id.in_(raw_ids)
            ).delete(synchronize_session=False)
        else:
            # SOFT DELETE: ⚠️ Kann UID-Konflikte beim Re-Fetch verursachen!
            from datetime import datetime, UTC
            deleted_raw = session.query(models.RawEmail).filter(
                models.RawEmail.id.in_(raw_ids)
            ).update(
                {"deleted_at": datetime.now(UTC)},
                synchronize_session=False
            )
        session.flush()
        
        # Reset initial_sync_done Flag & UIDVALIDITY Cache für betroffene Accounts
        # Damit beim nächsten Fetch wieder 500 Mails geholt werden (initial sync)
        account_query = session.query(models.MailAccount)
        if account_id:
            account_query = account_query.filter(models.MailAccount.id == account_id)
        elif user_id:
            account_query = account_query.filter(models.MailAccount.user_id == user_id)
        
        # Reset flags + UIDVALIDITY Cache
        affected_accounts = account_query.all()
        reset_accounts = 0
        for account in affected_accounts:
            account.initial_sync_done = False
            account.folder_uidvalidity = None  # Reset UIDVALIDITY cache
            reset_accounts += 1
        session.flush()
        
        session.commit()
        
        print()
        delete_mode = "HARD DELETE" if hard_delete else "SOFT DELETE (deleted_at)"
        print(f"✅ {deleted_processed} ProcessedEmail-Einträge gelöscht ({delete_mode})")
        print(f"✅ {deleted_raw} RawEmail-Einträge gelöscht ({delete_mode})")
        print(f"✅ {reset_accounts} Mail-Account(s) zurückgesetzt:")
        print(f"   - initial_sync_done = False")
        print(f"   - folder_uidvalidity = NULL (UIDVALIDITY Cache geleert)")
        print()
        
        if hard_delete:
            print("🔄 Beim nächsten 'E-Mails abrufen':")
            print("   - Werden alle E-Mails neu abgerufen (initial sync: 500 Mails)")
            print("   - UIDVALIDITY wird neu vom Server geholt")
            print("   - Keine UID-Konflikte (alte Records komplett gelöscht)")
            print("   - Komplett neu analysiert")
        else:
            print("⚠️  SOFT DELETE verwendet:")
            print("   - Records bleiben in DB mit deleted_at = NOW()")
            print("   - Audit-Trail erhalten (kann später wiederhergestellt werden)")
            print("   - ⚠️ ACHTUNG: UIDs bleiben in DB, Re-Fetch könnte 'Duplikate' melden")
            print("   - Für sauberen Neustart: --hard-delete verwenden")
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
        description="Lösche ALLE E-Mails (Raw + Processed) für kompletten Neustart",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python3 scripts/reset_all_emails.py              # Alle Emails löschen
  python3 scripts/reset_all_emails.py --account=1  # Nur Account 1
  python3 scripts/reset_all_emails.py --user=1     # Nur User 1
  python3 scripts/reset_all_emails.py --force      # Ohne Bestätigung

Hinweis:
  User-Account, Mail-Account-Daten und alle Settings bleiben erhalten!
  Nur die abgerufenen E-Mails und deren KI-Analysen werden gelöscht.
        """
    )
    parser.add_argument('--account', type=int, help='Nur für diese Mail-Account ID')
    parser.add_argument('--user', type=int, help='Nur für diese User ID')
    parser.add_argument('--force', action='store_true', help='Ohne Bestätigung löschen')
    parser.add_argument('--hard-delete', action='store_true', help='HARD DELETE (komplett löschen, keine UIDs in DB). Default: SOFT DELETE (deleted_at)')
    
    args = parser.parse_args()
    
    print("🧹 Reset All Emails Tool")
    print("=" * 70)
    print()
    
    success = reset_all_emails(
        account_id=args.account,
        user_id=args.user,
        force=args.force,
        hard_delete=args.hard_delete
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
