#!/usr/bin/env python3
"""
User Management CLI Tool - KI-Mail-Helper
Phase INV: Invite Whitelist & IMAP Diagnostics Access

Usage:
    python3 scripts/manage_users.py add-whitelist user@example.com
    python3 scripts/manage_users.py remove-whitelist user@example.com
    python3 scripts/manage_users.py list-whitelist
    python3 scripts/manage_users.py enable-diagnostics user@example.com
    python3 scripts/manage_users.py disable-diagnostics user@example.com
    python3 scripts/manage_users.py list-diagnostics
"""

import sys
import os
from datetime import datetime, UTC

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import models module
import importlib
models_module = importlib.import_module('src.02_models')
init_db = models_module.init_db
User = models_module.User
InvitedEmail = models_module.InvitedEmail

from sqlalchemy.orm import Session


def get_db():
    """Get database engine and session"""
    engine, SessionMaker = init_db()
    return engine, SessionMaker


def add_whitelist(email: str, invited_by: str = "CLI"):
    """Fügt eine Email zur Whitelist hinzu"""
    engine, SessionMaker = get_db()
    db: Session = SessionMaker()
    
    try:
        # Check if already exists
        existing = db.query(InvitedEmail).filter_by(email=email).first()
        if existing:
            if existing.used:
                print(f"❌ {email} wurde bereits für Registration verwendet (am {existing.used_at})")
            else:
                print(f"ℹ️  {email} ist bereits auf der Whitelist (seit {existing.invited_at})")
            return
        
        # Add new invite
        invite = InvitedEmail(
            email=email,
            invited_by=invited_by,
            invited_at=datetime.now(UTC)
        )
        db.add(invite)
        db.commit()
        print(f"✅ {email} zur Whitelist hinzugefügt")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Fehler: {e}")
    finally:
        db.close()


def remove_whitelist(email: str):
    """Entfernt eine Email von der Whitelist"""
    engine, SessionMaker = get_db()
    db: Session = SessionMaker()
    
    try:
        invite = db.query(InvitedEmail).filter_by(email=email).first()
        if not invite:
            print(f"❌ {email} ist nicht auf der Whitelist")
            return
        
        db.delete(invite)
        db.commit()
        print(f"✅ {email} von Whitelist entfernt")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Fehler: {e}")
    finally:
        db.close()


def list_whitelist():
    """Zeigt alle Whitelist-Einträge"""
    engine, SessionMaker = get_db()
    db: Session = SessionMaker()
    
    try:
        invites = db.query(InvitedEmail).order_by(InvitedEmail.invited_at.desc()).all()
        
        if not invites:
            print("📋 Whitelist ist leer")
            return
        
        print(f"\n📋 Whitelist ({len(invites)} Einträge):")
        print("=" * 80)
        print(f"{'Email':<40} {'Status':<15} {'Invited At':<20}")
        print("-" * 80)
        
        for invite in invites:
            status = "✅ Verwendet" if invite.used else "⏳ Offen"
            date_str = invite.invited_at.strftime("%Y-%m-%d %H:%M")
            print(f"{invite.email:<40} {status:<15} {date_str:<20}")
        
        print("=" * 80)
        
    finally:
        db.close()


def enable_diagnostics(email: str):
    """Aktiviert IMAP-Diagnostics für einen User"""
    engine, SessionMaker = get_db()
    db: Session = SessionMaker()
    
    try:
        user = db.query(User).filter_by(email=email).first()
        if not user:
            print(f"❌ User {email} nicht gefunden")
            return
        
        if user.imap_diagnostics_enabled:
            print(f"ℹ️  IMAP-Diagnostics für {email} bereits aktiviert")
            return
        
        user.imap_diagnostics_enabled = True
        db.commit()
        print(f"✅ IMAP-Diagnostics für {email} aktiviert")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Fehler: {e}")
    finally:
        db.close()


def disable_diagnostics(email: str):
    """Deaktiviert IMAP-Diagnostics für einen User"""
    engine, SessionMaker = get_db()
    db: Session = SessionMaker()
    
    try:
        user = db.query(User).filter_by(email=email).first()
        if not user:
            print(f"❌ User {email} nicht gefunden")
            return
        
        if not user.imap_diagnostics_enabled:
            print(f"ℹ️  IMAP-Diagnostics für {email} bereits deaktiviert")
            return
        
        user.imap_diagnostics_enabled = False
        db.commit()
        print(f"✅ IMAP-Diagnostics für {email} deaktiviert")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Fehler: {e}")
    finally:
        db.close()


def list_diagnostics():
    """Zeigt alle User mit IMAP-Diagnostics Zugriff"""
    engine, SessionMaker = get_db()
    db: Session = SessionMaker()
    
    try:
        users = db.query(User).filter_by(imap_diagnostics_enabled=True).all()
        
        if not users:
            print("📋 Keine User mit IMAP-Diagnostics Zugriff")
            return
        
        print(f"\n📋 User mit IMAP-Diagnostics Zugriff ({len(users)}):")
        print("=" * 60)
        print(f"{'Username':<30} {'Email':<30}")
        print("-" * 60)
        
        for user in users:
            print(f"{user.username:<30} {user.email:<30}")
        
        print("=" * 60)
        
    finally:
        db.close()


def show_help():
    """Zeigt die Hilfe"""
    print("""
📧 KI-Mail-Helper User Management Tool

WHITELIST (Registration-Kontrolle):
  add-whitelist <email>       Erlaube Registration für diese Email
  remove-whitelist <email>    Entferne Email von Whitelist
  list-whitelist              Zeige alle Whitelist-Einträge

IMAP-DIAGNOSTICS (Zugriffskontrolle):
  enable-diagnostics <email>  Aktiviere /imap-diagnostics für User
  disable-diagnostics <email> Deaktiviere /imap-diagnostics für User
  list-diagnostics            Zeige alle User mit Diagnostics-Zugriff

Beispiele:
  python3 scripts/manage_users.py add-whitelist max@example.com
  python3 scripts/manage_users.py enable-diagnostics max@example.com
  python3 scripts/manage_users.py list-whitelist
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_help()
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "add-whitelist":
        if len(sys.argv) < 3:
            print("❌ Email-Adresse fehlt: manage_users.py add-whitelist <email>")
            sys.exit(1)
        add_whitelist(sys.argv[2])
        
    elif command == "remove-whitelist":
        if len(sys.argv) < 3:
            print("❌ Email-Adresse fehlt: manage_users.py remove-whitelist <email>")
            sys.exit(1)
        remove_whitelist(sys.argv[2])
        
    elif command == "list-whitelist":
        list_whitelist()
        
    elif command == "enable-diagnostics":
        if len(sys.argv) < 3:
            print("❌ Email-Adresse fehlt: manage_users.py enable-diagnostics <email>")
            sys.exit(1)
        enable_diagnostics(sys.argv[2])
        
    elif command == "disable-diagnostics":
        if len(sys.argv) < 3:
            print("❌ Email-Adresse fehlt: manage_users.py disable-diagnostics <email>")
            sys.exit(1)
        disable_diagnostics(sys.argv[2])
        
    elif command == "list-diagnostics":
        list_diagnostics()
        
    else:
        print(f"❌ Unbekannter Befehl: {command}")
        show_help()
        sys.exit(1)
