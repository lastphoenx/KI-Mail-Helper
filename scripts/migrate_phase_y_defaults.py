#!/usr/bin/env python3
"""
P2-009: Phase Y Migration für bestehende Accounts

Erstellt SpacyScoringConfig und SpacyUserDomain für alle bestehenden
MailAccounts die noch keine haben.

Usage:
    python scripts/migrate_phase_y_defaults.py [--dry-run]
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import argparse
from datetime import datetime, UTC
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import importlib

# Import models dynamically
models = importlib.import_module("02_models", "src")
encryption = importlib.import_module("08_encryption", "src")

Base = models.Base
User = models.User
MailAccount = models.MailAccount
SpacyScoringConfig = models.SpacyScoringConfig
SpacyUserDomain = models.SpacyUserDomain
CredentialManager = encryption.CredentialManager

# Database setup
DATABASE_PATH = Path(__file__).parent.parent / "emails.db"
engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


def extract_email_domain(encrypted_username: bytes, master_key: str) -> str | None:
    """Extrahiert Domain aus verschlüsselter Email-Adresse"""
    try:
        email = CredentialManager.decrypt_email_address(encrypted_username, master_key)
        if '@' in email:
            return email.split('@')[1]
        return None
    except Exception:
        return None


def migrate_account(db, account: MailAccount, master_key: str = None, dry_run: bool = False):
    """Migriert einen einzelnen Account zu Phase Y Defaults"""
    results = {
        'config_created': False,
        'domain_created': False,
        'errors': []
    }
    
    try:
        # 1. SpacyScoringConfig
        existing_config = db.query(SpacyScoringConfig).filter_by(
            user_id=account.user_id,
            account_id=account.id
        ).first()
        
        if not existing_config:
            if not dry_run:
                config = SpacyScoringConfig(
                    user_id=account.user_id,
                    account_id=account.id,
                    imperative_weight=3,
                    deadline_weight=4,
                    keyword_weight=2,
                    vip_weight=3,
                    question_threshold=3,
                    negation_sensitivity=2,
                    spacy_weight_initial=100,
                    spacy_weight_learning=30,
                    spacy_weight_trained=15
                )
                db.add(config)
            results['config_created'] = True
        
        # 2. SpacyUserDomain (wenn Email-Domain extrahierbar)
        email_domain = None
        if master_key and account.encrypted_imap_username:
            email_domain = extract_email_domain(account.encrypted_imap_username, master_key)
        
        if email_domain:
            existing_domain = db.query(SpacyUserDomain).filter_by(
                account_id=account.id,
                domain=email_domain
            ).first()
            
            if not existing_domain:
                if not dry_run:
                    user_domain = SpacyUserDomain(
                        user_id=account.user_id,
                        account_id=account.id,
                        domain=email_domain,
                        is_active=True
                    )
                    db.add(user_domain)
                results['domain_created'] = True
        
        if not dry_run:
            db.commit()
        
    except Exception as e:
        results['errors'].append(str(e))
        if not dry_run:
            db.rollback()
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Migrate existing accounts to Phase Y defaults')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--master-key', type=str, help='Master key for email domain extraction (optional)')
    args = parser.parse_args()
    
    db = SessionLocal()
    
    try:
        # Get all accounts
        accounts = db.query(MailAccount).join(User).filter(MailAccount.enabled == True).all()
        
        print(f"{'[DRY RUN] ' if args.dry_run else ''}Found {len(accounts)} enabled accounts")
        print("=" * 70)
        
        stats = {
            'total': len(accounts),
            'configs_created': 0,
            'domains_created': 0,
            'errors': 0
        }
        
        for account in accounts:
            print(f"\n📧 Account {account.id}: {account.name} (User: {account.user.username})")
            
            results = migrate_account(db, account, args.master_key, args.dry_run)
            
            if results['config_created']:
                print(f"  ✅ SpacyScoringConfig {'would be created' if args.dry_run else 'created'}")
                stats['configs_created'] += 1
            else:
                print(f"  ⏭️  SpacyScoringConfig already exists")
            
            if results['domain_created']:
                print(f"  ✅ SpacyUserDomain {'would be created' if args.dry_run else 'created'}")
                stats['domains_created'] += 1
            elif args.master_key:
                print(f"  ⏭️  SpacyUserDomain already exists or no domain found")
            else:
                print(f"  ⚠️  No master key provided - cannot extract email domain")
            
            if results['errors']:
                print(f"  ❌ Errors: {', '.join(results['errors'])}")
                stats['errors'] += 1
        
        print("\n" + "=" * 70)
        print("📊 SUMMARY")
        print(f"  Total Accounts: {stats['total']}")
        print(f"  Configs {'to create' if args.dry_run else 'created'}: {stats['configs_created']}")
        print(f"  Domains {'to create' if args.dry_run else 'created'}: {stats['domains_created']}")
        print(f"  Errors: {stats['errors']}")
        
        if args.dry_run:
            print("\n💡 Run without --dry-run to apply changes")
        else:
            print("\n✅ Migration complete!")
    
    finally:
        db.close()


if __name__ == "__main__":
    main()
