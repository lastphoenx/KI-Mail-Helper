#!/usr/bin/env python3
"""
Reset All Emails – Löscht alle RawEmails und ProcessedEmails,
damit beim nächsten Abrufen alles neu abgerufen und verarbeitet wird.

User-Account und Mail-Account-Daten bleiben erhalten!

Verwendung:
  python3 scripts/reset_all_emails.py --list       # Übersicht aller User und Accounts
  python3 scripts/reset_all_emails.py              # Alle Emails
  python3 scripts/reset_all_emails.py --account=1  # Nur Account ID 1
  python3 scripts/reset_all_emails.py --user=1     # Nur User ID 1
  python3 scripts/reset_all_emails.py --email=4,5,6  # Nur bestimmte Email IDs
  python3 scripts/reset_all_emails.py --force      # Ohne Bestätigung
  python3 scripts/reset_all_emails.py --clean-sanitization  # Nur Sanitization-Daten löschen
  python3 scripts/reset_all_emails.py --email=4 --clean-sanitization  # Sanitization nur für Email 4

Vorsicht: Worker sollte während des Löschens NICHT laufen!
"""

import sys
import os
import importlib
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
models = importlib.import_module('.02_models', 'src')


def list_users_accounts():
    """Zeigt eine Übersicht aller User und deren Mail-Accounts mit Email-Statistiken"""
    engine, Session = models.init_db("emails.db")
    session = Session()
    
    try:
        # Alle User mit ihren Accounts laden
        users = session.query(models.User).order_by(models.User.id).all()
        
        if not users:
            print("ℹ️  Keine User in der Datenbank gefunden.")
            return True
        
        print("📋 Übersicht: User und Mail-Accounts")
        print("=" * 90)
        print(f"{'User ID':<10} {'Username':<20} {'Account ID':<12} {'Account Name':<25} {'Emails':<10}")
        print("-" * 90)
        
        total_users = 0
        total_accounts = 0
        total_emails = 0
        
        for user in users:
            total_users += 1
            accounts = session.query(models.MailAccount).filter(
                models.MailAccount.user_id == user.id
            ).order_by(models.MailAccount.id).all()
            
            if not accounts:
                # User ohne Accounts
                print(f"{user.id:<10} {user.username:<20} {'-':<12} {'(keine Accounts)':<25} {'-':<10}")
            else:
                for i, account in enumerate(accounts):
                    total_accounts += 1
                    # Emails für diesen Account zählen
                    email_count = session.query(models.RawEmail).filter(
                        models.RawEmail.mail_account_id == account.id,
                        models.RawEmail.deleted_at.is_(None)
                    ).count()
                    total_emails += email_count
                    
                    if i == 0:
                        # Erste Zeile: User-Info + Account
                        print(f"{user.id:<10} {user.username:<20} {account.id:<12} {account.name:<25} {email_count:<10}")
                    else:
                        # Folgezeilen: Nur Account (User-Spalten leer)
                        print(f"{'':<10} {'':<20} {account.id:<12} {account.name:<25} {email_count:<10}")
        
        print("-" * 90)
        print(f"{'Gesamt:':<10} {total_users} User{'':<14} {total_accounts} Accounts{'':<16} {total_emails} Emails")
        print()
        return True
        
    except Exception as e:
        print(f"❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()


def clean_sanitization_data(email_ids=None, account_id=None, user_id=None, force=False):
    """Löscht nur die Sanitization-Daten (anonymisierte Felder) von RawEmails
    
    Args:
        email_ids: Liste von Email-IDs (oder None für alle)
        account_id: Nur für diesen Account
        user_id: Nur für diesen User
        force: Ohne Bestätigung
    """
    engine, Session = models.init_db("emails.db")
    session = Session()
    
    try:
        query = session.query(models.RawEmail)
        scope_desc = "alle Emails"
        
        if email_ids:
            query = query.filter(models.RawEmail.id.in_(email_ids))
            scope_desc = f"Email IDs {email_ids}"
        elif account_id:
            query = query.filter(models.RawEmail.mail_account_id == account_id)
            scope_desc = f"Account ID {account_id}"
        elif user_id:
            query = query.filter(models.RawEmail.user_id == user_id)
            scope_desc = f"User ID {user_id}"
        
        count = query.count()
        
        if count == 0:
            print(f"ℹ️  Keine E-Mails gefunden für {scope_desc}")
            return True
        
        print(f"🧹 Sanitization-Daten bereinigen:")
        print(f"   📧 {count} RawEmail-Einträge betroffen ({scope_desc})")
        print()
        print(f"   Folgende Felder werden auf NULL gesetzt:")
        print(f"   - encrypted_subject_sanitized")
        print(f"   - encrypted_body_sanitized")
        print(f"   - sanitization_entities_count")
        print(f"   - sanitization_level")
        print(f"   - sanitization_time_ms")
        print()
        
        if not force:
            confirm = input("🚨 Wirklich Sanitization-Daten löschen? [y/N]: ").strip().lower()
            if confirm != 'y':
                print("❌ Abgebrochen")
                return False
        
        # Update durchführen
        affected = query.update({
            "encrypted_subject_sanitized": None,
            "encrypted_body_sanitized": None,
            "sanitization_entities_count": None,
            "sanitization_level": None,
            "sanitization_time_ms": None
        }, synchronize_session=False)
        
        session.commit()
        
        print()
        print(f"✅ {affected} Email(s) bereinigt - Sanitization-Daten gelöscht!")
        print(f"🔄 Beim nächsten Verarbeiten werden die Emails neu anonymisiert.")
        return True
        
    except Exception as e:
        session.rollback()
        print(f"❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()


def reset_all_emails(account_id=None, user_id=None, email_ids=None, force=False, hard_delete=False):
    """Löscht RawEmail UND ProcessedEmail Einträge für kompletten Neustart
    
    Args:
        account_id: Nur für diesen Account
        user_id: Nur für diesen User
        email_ids: Liste von spezifischen Email-IDs (oder None für alle)
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
        if email_ids:
            raw_query = raw_query.filter(models.RawEmail.id.in_(email_ids))
            scope_desc = f"Email IDs {email_ids}"
        elif account_id:
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
        
        # ProcessedEmails löschen (wegen Foreign Key)
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
        
        # ════════════════════════════════════════════════════════════════
        # mail_server_state.raw_email_id auf NULL setzen (FK-Constraint!)
        # ════════════════════════════════════════════════════════════════
        if hasattr(models, 'MailServerState'):
            updated_server_state = session.query(models.MailServerState).filter(
                models.MailServerState.raw_email_id.in_(raw_ids)
            ).update(
                {"raw_email_id": None},
                synchronize_session=False
            )
            if updated_server_state > 0:
                print(f"   🔗 {updated_server_state} mail_server_state-Einträge entkoppelt")
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
        # ABER: Nicht bei einzelnen Email-IDs, da wir nicht den ganzen Account zurücksetzen wollen
        reset_accounts = 0
        if not email_ids:
            account_query = session.query(models.MailAccount)
            if account_id:
                account_query = account_query.filter(models.MailAccount.id == account_id)
            elif user_id:
                account_query = account_query.filter(models.MailAccount.user_id == user_id)
            
            # Reset flags + UIDVALIDITY Cache
            affected_accounts = account_query.all()
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
        print(f"ℹ️  MailServerState bleibt als Audit-Trail (raw_email_id wurde auf NULL gesetzt)")
        if reset_accounts > 0:
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
  python3 scripts/reset_all_emails.py                         # Alle Emails löschen
  python3 scripts/reset_all_emails.py --account=1             # Nur Account 1
  python3 scripts/reset_all_emails.py --user=1                # Nur User 1
  python3 scripts/reset_all_emails.py --email=4,5,6           # Nur Email IDs 4, 5, 6
  python3 scripts/reset_all_emails.py --email=4               # Nur Email ID 4
  python3 scripts/reset_all_emails.py --force                 # Ohne Bestätigung
  python3 scripts/reset_all_emails.py --clean-sanitization    # Nur Sanitization-Daten löschen
  python3 scripts/reset_all_emails.py --email=4 --clean-sanitization  # Sanitization nur für Email 4

Hinweis:
  User-Account, Mail-Account-Daten und alle Settings bleiben erhalten!
  Nur die abgerufenen E-Mails und deren KI-Analysen werden gelöscht.
        """
    )
    parser.add_argument('--list', action='store_true', help='Zeige Übersicht aller User und Accounts mit Email-Anzahl')
    parser.add_argument('--account', type=int, help='Nur für diese Mail-Account ID')
    parser.add_argument('--user', type=int, help='Nur für diese User ID')
    parser.add_argument('--email', type=str, help='Komma-getrennte Liste von Email IDs (z.B. --email=4 oder --email=4,5,6)')
    parser.add_argument('--force', action='store_true', help='Ohne Bestätigung löschen')
    parser.add_argument('--hard-delete', action='store_true', help='HARD DELETE (komplett löschen, keine UIDs in DB). Default: SOFT DELETE (deleted_at)')
    parser.add_argument('--clean-sanitization', action='store_true', help='Nur Sanitization-Daten löschen (anonymisierte Felder auf NULL setzen)')
    
    args = parser.parse_args()
    
    # Email IDs parsen
    email_ids = None
    if args.email:
        try:
            email_ids = [int(x.strip()) for x in args.email.split(',')]
        except ValueError:
            print("❌ Ungültige Email IDs. Format: --email=4 oder --email=4,5,6")
            sys.exit(1)
    
    print("🧹 Reset All Emails Tool")
    print("=" * 70)
    print()
    
    # Wenn --list, dann Übersicht anzeigen und beenden
    if args.list:
        success = list_users_accounts()
        sys.exit(0 if success else 1)
    
    # Wenn --clean-sanitization, dann nur Sanitization-Daten löschen
    if args.clean_sanitization:
        success = clean_sanitization_data(
            email_ids=email_ids,
            account_id=args.account,
            user_id=args.user,
            force=args.force
        )
    else:
        success = reset_all_emails(
            account_id=args.account,
            user_id=args.user,
            email_ids=email_ids,
            force=args.force,
            hard_delete=args.hard_delete
        )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
