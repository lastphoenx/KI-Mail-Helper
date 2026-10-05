#!/usr/bin/env python3
"""
Migration: Erstellt Tabelle audit_auto_delete_rules für automatische Lösch-Regeln.

Disposition-basierte Regeln mit Sender + Subject Patterns.

Usage:
    python migrations/add_audit_auto_delete_rules.py
"""
import sys
import os
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set environment for DB connection
os.environ.setdefault("PYTHONPATH", str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def get_db_url():
    """Lädt DB-URL aus Umgebung oder .env"""
    # Erst Environment-Variable prüfen
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        return db_url
    
    # .env Datei lesen
    env_file = project_root / ".env"
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    
    # Default für lokale Entwicklung
    return "postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper"


def run_migration():
    """Erstellt die audit_auto_delete_rules Tabelle."""
    
    db_url = get_db_url()
    print(f"Connecting to: {db_url.split('@')[-1]}")  # Nur Host/DB zeigen
    
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    
    with Session() as session:
        # Prüfen ob Tabelle existiert
        result = session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'audit_auto_delete_rules'
            )
        """))
        exists = result.scalar()
        
        if exists:
            print("✓ Tabelle audit_auto_delete_rules existiert bereits")
            return
        
        # Tabelle erstellen
        session.execute(text("""
            CREATE TABLE audit_auto_delete_rules (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                account_id INTEGER REFERENCES mail_accounts(id) ON DELETE CASCADE,
                sender_pattern VARCHAR(255),
                subject_pattern VARCHAR(255),
                disposition VARCHAR(20) NOT NULL,
                max_age_days INTEGER,
                description VARCHAR(255),
                source VARCHAR(20) NOT NULL DEFAULT 'user',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                
                CONSTRAINT uq_audit_auto_delete_rule 
                    UNIQUE (user_id, account_id, sender_pattern, subject_pattern),
                CONSTRAINT ck_audit_auto_delete_disposition 
                    CHECK (disposition IN ('DELETABLE', 'PROTECTED', 'JUNK')),
                CONSTRAINT ck_audit_auto_delete_has_pattern 
                    CHECK (sender_pattern IS NOT NULL OR subject_pattern IS NOT NULL)
            )
        """))
        
        # Index erstellen
        session.execute(text("""
            CREATE INDEX idx_audit_auto_delete_user 
            ON audit_auto_delete_rules(user_id, account_id)
        """))
        
        session.commit()
        print("✓ Tabelle audit_auto_delete_rules erstellt")
        
        # Beispiel-Regeln einfügen (für User 1 falls vorhanden)
        user_result = session.execute(text("SELECT id FROM users LIMIT 1"))
        user = user_result.fetchone()
        
        if user:
            user_id = user[0]
            
            example_rules = [
                # Newsletter allgemein
                ("@newsletter.", None, "DELETABLE", 14, "Newsletter-Subdomains"),
                # Marketing Plattformen
                ("@mailchimp.", None, "DELETABLE", 7, "Mailchimp Marketing"),
                ("@sendgrid.", None, "DELETABLE", 7, "SendGrid Marketing"),
                # Cron/System-Mails
                ("cron@", None, "DELETABLE", 1, "Cron-Job Mails"),
                ("root@", None, "DELETABLE", 3, "Root System-Mails"),
                # Erfolgreiche Backups
                (None, r"backup.*success|erfolgreich.*backup", "DELETABLE", 3, "Erfolgreiche Backups"),
                # Behörden schützen
                ("@admin.ch", None, "PROTECTED", None, "Schweizer Behörden"),
                ("@estv.admin.ch", None, "PROTECTED", None, "Steuerverwaltung"),
            ]
            
            for sender, subject, disposition, max_age, desc in example_rules:
                try:
                    session.execute(text("""
                        INSERT INTO audit_auto_delete_rules 
                        (user_id, sender_pattern, subject_pattern, disposition, max_age_days, description)
                        VALUES (:user_id, :sender, :subject, :disposition, :max_age, :desc)
                        ON CONFLICT DO NOTHING
                    """), {
                        "user_id": user_id,
                        "sender": sender,
                        "subject": subject,
                        "disposition": disposition,
                        "max_age": max_age,
                        "desc": desc
                    })
                except Exception as e:
                    print(f"  Warnung bei Regel {sender}/{subject}: {e}")
            
            session.commit()
            print(f"✓ {len(example_rules)} Beispiel-Regeln für User {user_id} eingefügt")


def rollback_migration():
    """Entfernt die audit_auto_delete_rules Tabelle."""
    
    with models.db_session() as session:
        session.execute(text("DROP TABLE IF EXISTS audit_auto_delete_rules CASCADE"))
        session.commit()
        print("✓ Tabelle audit_auto_delete_rules entfernt")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", action="store_true", help="Migration rückgängig machen")
    args = parser.parse_args()
    
    if args.rollback:
        rollback_migration()
    else:
        run_migration()
