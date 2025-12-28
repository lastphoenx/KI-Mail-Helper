"""
Mail Helper - Entry Point
Hauptprogramm mit CLI-Optionen und Orchestrierung
"""

import os
from dotenv import load_dotenv

load_dotenv()

import argparse
import sys
import logging
import json
from pathlib import Path
from datetime import datetime

import importlib
models = importlib.import_module('.02_models', 'src')
mail_fetcher = importlib.import_module('.06_mail_fetcher', 'src')
sanitizer = importlib.import_module('.04_sanitizer', 'src')
ai_client = importlib.import_module('.03_ai_client', 'src')
scoring = importlib.import_module('.05_scoring', 'src')
web_app = importlib.import_module('.01_web_app', 'src')
encryption = importlib.import_module('.08_encryption', 'src')
auth = importlib.import_module('.07_auth', 'src')
google_oauth = importlib.import_module('.10_google_oauth', 'src')
processing = importlib.import_module('.12_processing', 'src')
ai_pref_migration = importlib.import_module('.13_migrate_ai_preferences', 'src')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATABASE_PATH = "emails.db"
MAX_EMAILS_PER_REQUEST = 1000  # Layer 4 Security: Resource Exhaustion Prevention


def init_db():
    """Initialisiert die Datenbank"""
    logger.info("📊 Initialisiere Datenbank...")
    engine, Session = models.init_db(DATABASE_PATH)
    ai_pref_migration.ensure_ai_preferences_columns(DATABASE_PATH)
    logger.info(f"✅ Datenbank bereit: {DATABASE_PATH}")
    return engine, Session


def fetch_and_process(max_mails: int = 50, user_id: int = None, master_keys: dict = None):
    """Holt neue Mails und verarbeitet sie
    
    Args:
        max_mails: Max. Mails pro Account (max 1000)
        user_id: Spezifischer User (None = alle)
        master_keys: Dict von user_id -> master_key für Entschlüsselung
    """
    if max_mails > MAX_EMAILS_PER_REQUEST:
        raise ValueError(f"max_mails darf maximal {MAX_EMAILS_PER_REQUEST} sein (gegeben: {max_mails})")
    
    if master_keys is None:
        master_keys = {}
    
    engine, Session = init_db()
    session = Session()
    
    try:
        logger.info("🚀 Starte Mail-Verarbeitung...")

        processed_count_total = 0

        users_query = session.query(models.User)
        if user_id:
            users_query = users_query.filter_by(id=user_id)

        users = users_query.all()

        if not users:
            logger.info("ℹ️  Keine User in der Datenbank")
            return True

        for user in users:
            logger.info(f"👤 Verarbeite User (ID: {user.id})")

            provider = (getattr(user, "preferred_ai_provider", None) or "ollama").lower()
            requested_model = getattr(user, "preferred_ai_model", None)
            try:
                user_ai = ai_client.build_client(provider, model=requested_model)
            except Exception as exc:
                logger.error(
                    "⚠️ Konnte KI-Client %s für %s nicht initialisieren: %s. Fallback auf Ollama.",
                    provider,
                    user.username,
                    exc
                )
                provider = "ollama"
                user_ai = ai_client.build_client("ollama")

            user_sanitize_level = sanitizer.get_sanitization_level(
                ai_client.provider_requires_cloud(provider)
            )

            mail_accounts = session.query(models.MailAccount).filter_by(
                user_id=user.id,
                enabled=True
            ).all()

            if not mail_accounts:
                logger.info(f"ℹ️  User (ID: {user.id}) hat keine Mail-Accounts")
                continue

            user_master_key = master_keys.get(user.id)

            if not user_master_key:
                logger.warning(
                    f"⚠️  Zero-Knowledge: Master-Key für User (ID: {user.id}) nicht in Session. "
                    "User muss eingeloggt sein und 'Abrufen' klicken."
                )
                continue

            for mail_account in mail_accounts:
                raw_emails = []
                skip_fetch = False

                try:
                    logger.info(f"📧 Hole Mails von: {mail_account.name}")

                    if mail_account.oauth_provider == "google":
                        if not user_master_key:
                            logger.error(
                                f"❌ Master-Key fehlt für OAuth Account {mail_account.name}. Überspringe Fetch."
                            )
                            skip_fetch = True
                        else:
                            try:
                                decrypted_token = encryption.CredentialManager.decrypt_imap_password(
                                    mail_account.encrypted_oauth_token,
                                    user_master_key
                                )
                                fetcher = google_oauth.GoogleMailFetcher(access_token=decrypted_token)
                                raw_emails = fetcher.fetch_new_emails(limit=max_mails)
                            except Exception as e:
                                logger.error(f"❌ Google OAuth Fehler für {mail_account.name}: {e}")
                                skip_fetch = True
                    else:
                        if not mail_account.encrypted_imap_password:
                            logger.warning(
                                f"⚠️  Kein IMAP-Passwort gespeichert für {mail_account.name}. Überspringe Fetch."
                            )
                            skip_fetch = True
                        elif not user_master_key:
                            logger.error(
                                f"❌ Master-Key fehlt für Account {mail_account.name}. Überspringe Fetch."
                            )
                            skip_fetch = True
                        else:
                            try:
                                # Zero-Knowledge: Entschlüssele IMAP-Credentials
                                imap_password = encryption.CredentialManager.decrypt_imap_password(
                                    mail_account.encrypted_imap_password,
                                    user_master_key
                                )
                                imap_server = encryption.CredentialManager.decrypt_server(
                                    mail_account.encrypted_imap_server,
                                    user_master_key
                                )
                                imap_username = encryption.CredentialManager.decrypt_email_address(
                                    mail_account.encrypted_imap_username,
                                    user_master_key
                                )
                                
                                fetcher = mail_fetcher.MailFetcher(
                                    server=imap_server,
                                    username=imap_username,
                                    password=imap_password,
                                    port=mail_account.imap_port
                                )
                                fetcher.connect()
                                try:
                                    raw_emails = fetcher.fetch_new_emails(limit=max_mails)
                                finally:
                                    fetcher.disconnect()
                            except Exception as e:
                                logger.error(f"❌ IMAP Fehler für {mail_account.name}: {e}")
                                skip_fetch = True

                    saved_count = 0
                    if skip_fetch:
                        logger.info(
                            f"⏭️  Fetch übersprungen für {mail_account.name}, verarbeite vorhandene Mails."
                        )
                    elif not raw_emails:
                        logger.info(f"ℹ️  Keine neuen Mails in {mail_account.name}")
                    else:
                        logger.info(f"📥 {len(raw_emails)} neue Mails in {mail_account.name}")
                        for raw_email_data in raw_emails:
                            existing = session.query(models.RawEmail).filter_by(
                                user_id=user.id,
                                mail_account_id=mail_account.id,
                                uid=raw_email_data["uid"]
                            ).first()

                            if existing:
                                logger.info(f"⏭️  Mail {raw_email_data['uid']} bereits gespeichert")
                                continue

                            # Zero-Knowledge: Verschlüssele E-Mail-Inhalte
                            encrypted_sender = encryption.EmailDataManager.encrypt_email_sender(
                                raw_email_data["sender"],
                                user_master_key
                            )
                            encrypted_subject = encryption.EmailDataManager.encrypt_email_subject(
                                raw_email_data["subject"],
                                user_master_key
                            )
                            encrypted_body = encryption.EmailDataManager.encrypt_email_body(
                                raw_email_data["body"],
                                user_master_key
                            )
                            
                            raw_email = models.RawEmail(
                                user_id=user.id,
                                mail_account_id=mail_account.id,
                                uid=raw_email_data["uid"],
                                encrypted_sender=encrypted_sender,
                                encrypted_subject=encrypted_subject,
                                encrypted_body=encrypted_body,
                                received_at=raw_email_data["received_at"],
                                imap_uid=raw_email_data.get("imap_uid"),
                                imap_folder=raw_email_data.get("imap_folder"),
                                imap_flags=raw_email_data.get("imap_flags"),
                            )
                            session.add(raw_email)
                            saved_count += 1

                        if saved_count:
                            session.commit()
                            logger.info(f"💾 {saved_count} neue RawEmails gespeichert in {mail_account.name}")
                        else:
                            session.flush()

                except Exception as e:
                    logger.error(f"❌ Fehler für Account {mail_account.name}: {e}")
                    session.rollback()
                finally:
                    processed = processing.process_pending_raw_emails(
                        session=session,
                        user=user,
                        master_key=user_master_key,
                        mail_account=mail_account,
                        limit=max_mails,
                        ai=user_ai,
                        sanitize_level=user_sanitize_level
                    )
                    processed_count_total += processed

        logger.info(f"🎉 Fertig! {processed_count_total} Mails verarbeitet")
        return True

    except Exception as e:
        logger.error(f"❌ Kritischer Fehler: {e}")
        return False

    finally:
        session.close()


def main():
    """Hauptfunktion mit CLI-Parsing"""
    parser = argparse.ArgumentParser(
        description="Mail Helper - Lokaler KI-Mail-Assistent"
    )
    
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Startet den Web-Server (Dashboard)"
    )
    
    parser.add_argument(
        "--process-once",
        action="store_true",
        help="Holt und verarbeitet Mails einmalig"
    )
    
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="Holt nur neue Mails (ohne KI-Verarbeitung)"
    )
    
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Initialisiert die Datenbank"
    )
    
    parser.add_argument(
        "--max-mails",
        type=int,
        default=50,
        help="Max. Anzahl Mails zu verarbeiten (default: 50)"
    )
    
    parser.add_argument(
        "--master-keys",
        help="JSON-formatierte Master-Keys als {user_id: key} (für Background-Jobs)"
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Web-Server Host (default: 0.0.0.0)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Web-Server Port (default: 5000)"
    )
    
    parser.add_argument(
        "--https",
        action="store_true",
        help="HTTPS aktivieren (Self-signed Certificate für Development)"
    )
    
    args = parser.parse_args()
    
    # Security: Validate host/port arguments (Defense-in-Depth)
    # Flask validates internally, but explicit check prevents potential issues
    if args.serve:
        import ipaddress
        try:
            # Allow localhost, 0.0.0.0, or valid IP addresses
            if args.host not in ['localhost', '0.0.0.0']:
                ipaddress.ip_address(args.host)
        except ValueError:
            logger.error(f"❌ Ungültiger Host: {args.host} (muss IP-Adresse, 'localhost' oder '0.0.0.0' sein)")
            sys.exit(1)
        
        if not (1024 <= args.port <= 65535):
            logger.error(f"❌ Ungültiger Port: {args.port} (muss zwischen 1024 und 65535 liegen)")
            sys.exit(1)
    
    if args.serve:
        logger.info("🌐 Starte Web-Dashboard...")
        init_db()
        web_app.start_server(host=args.host, port=args.port, debug=False, use_https=args.https)
        return 0
        
    elif args.process_once:
        logger.info("📧 Hole und verarbeite Mails einmalig...")
        master_keys = {}
        if args.master_keys:
            # DEPRECATED: CLI-Args sind in 'ps aux' sichtbar (Security-Risk)
            logger.warning("⚠️  Master-Keys via CLI sind unsicher (ps aux)! Besser: stdin ohne --master-keys")
            try:
                master_keys = json.loads(args.master_keys)
                master_keys = {int(k): v for k, v in master_keys.items()}
            except json.JSONDecodeError as e:
                logger.error(f"❌ Ungültiges Master-Keys JSON-Format: {e}")
                return 1
        else:
            # SECURE: Master-Keys via stdin (nicht in ps aux sichtbar)
            import getpass
            try:
                keys_input = getpass.getpass("Master-Keys JSON (oder Enter für leer): ")
                if keys_input.strip():
                    master_keys = json.loads(keys_input)
                    master_keys = {int(k): v for k, v in master_keys.items()}
                    logger.info("✅ Master-Keys erfolgreich geladen (via stdin)")
            except json.JSONDecodeError as e:
                logger.error(f"❌ Ungültiges Master-Keys JSON-Format: {e}")
                return 1
            except (KeyboardInterrupt, EOFError):
                logger.info("❌ Abbruch durch User")
                return 1
        
        try:
            success = fetch_and_process(max_mails=args.max_mails, master_keys=master_keys)
        except ValueError as e:
            logger.error(f"❌ {e}")
            return 1
        return 0 if success else 1
        
    elif args.fetch_only:
        logger.info("📥 Hole nur neue Mails...")
        init_db()
        imap_server = os.getenv("IMAP_SERVER")
        imap_user = os.getenv("IMAP_USERNAME")
        imap_password = os.getenv("IMAP_PASSWORD")
        
        if not all([imap_server, imap_user, imap_password]):
            logger.error("❌ IMAP-Anmeldedaten fehlen in .env")
            return 1
        
        fetcher = mail_fetcher.MailFetcher(imap_server, imap_user, imap_password)
        fetcher.connect()
        raw_emails = fetcher.fetch_new_emails(limit=args.max_mails)
        fetcher.disconnect()
        
        logger.info(f"✅ {len(raw_emails)} Mails abgerufen")
        return 0
    
    elif args.init_db:
        logger.info("📊 Initialisiere Datenbank...")
        init_db()
        logger.info("✅ Datenbank erfolgreich initialisiert")
        return 0
        
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
