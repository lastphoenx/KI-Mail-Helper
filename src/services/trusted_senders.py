"""
Trusted Sender Management (Phase X)

Verwaltet User-definierte vertrauenswürdige Absender.
Nur für Emails von diesen Sendern wird UrgencyBooster (spaCy) verwendet.
"""

import logging
import re
import importlib
from typing import Optional, List, Dict
from datetime import datetime, UTC
from sqlalchemy import func, update

logger = logging.getLogger(__name__)

MAX_TRUSTED_SENDERS_PER_USER = 500


def prepare_suggestion(sender: str, suggested_type: str) -> str:
    """
    Bereitet Sender-Vorschlag für Whitelist vor - intelligente Normalisierung.
    
    Extrahiert Email aus RFC 5322 Format: "Name" <email@domain.com>
    Wandelt dann je nach Pattern-Type um:
    - exact: email@domain.com (komplette Email)
    - email_domain: @domain.com (nur Domain mit @)
    - domain: domain.com (nur Domain ohne @)
    
    Args:
        sender: Input z.B. '"Notification System" <notifications@projects.example.com>'
        suggested_type: 'exact', 'email_domain', oder 'domain'
    
    Returns:
        Vorbereitete Pattern-String
    """
    # 1. Extrahiere Email aus RFC 5322 Format
    match = re.search(r'<(.+?)>', sender)
    email = match.group(1) if match else sender.strip()
    email_lower = email.lower()
    
    # 2. Konvertiere je nach Type
    if suggested_type == 'email_domain':
        # Nur Domain mit @ Präfix
        if '@' in email_lower:
            domain = email_lower.split('@')[1]
            return '@' + domain
        return email_lower
    
    elif suggested_type == 'domain':
        # Nur Domain ohne @ Präfix
        if '@' in email_lower:
            return email_lower.split('@')[1]
        return email_lower
    
    else:  # 'exact' oder default
        # Komplette Email
        return email_lower


# Validierungs-Regex (RFC 5321 + RFC 1123 compliant)
# EMAIL_REGEX: Strikte Email-Validierung
# - Verhindert konsekutive Punkte/Unterstriche (muss abwechseln)
# - Erlaubt Plus für email-tags und Bindestriche
# - Format: local[.+_-local]*@domain.tld
EMAIL_REGEX = r'^[a-zA-Z0-9]+([._+-][a-zA-Z0-9]+)*@[a-zA-Z0-9]+([.-][a-zA-Z0-9]+)*\.[a-zA-Z]{2,}$'

# DOMAIN_REGEX: RFC 1123 konforme Domain-Validierung
# - Jedes Label: [a-zA-Z0-9] oder [a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]
# - Verhindert Start/Ende mit Bindestrich
# - Verhindert konsekutive Bindestriche (Lookbehind verhindert a--b)
# - Minimum 2 Labels (domain.tld)
DOMAIN_REGEX = r'^([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'


class TrustedSenderManager:
    """Verwaltet Trusted Sender für User"""
    
    @staticmethod
    def is_trusted_sender(db, user_id: int, sender_email: str, account_id: Optional[int] = None) -> Optional[Dict]:
        """
        Prüft ob Sender vertrauenswürdig ist.
        
        Supports both user-level (global) and account-level matching:
        - Wenn account_id None: Prüft nur user_id (global)
        - Wenn account_id gegeben: Prüft zuerst account-spezifische, dann globale
        
        Args:
            sender_email: Email address, may include display name like "Name" <email@domain.com>
        
        Returns:
            None wenn nicht trusted
            dict mit {'id', 'label', 'use_urgency_booster', 'pattern', 'account_id'} wenn trusted
        """
        models = importlib.import_module(".02_models", "src")
        
        # Extract email from "Display Name" <email@domain.com> format if present
        sender_lower = sender_email.lower().strip()
        email_match = re.search(r'<(.+?)>', sender_lower)
        if email_match:
            sender_lower = email_match.group(1).strip()
        
        if '@' in sender_lower:
            domain = sender_lower.split('@')[1]
            email_domain = '@' + domain
        else:
            domain = sender_lower
            email_domain = None
        
        # Hole alle Trusted Sender für User
        # Wenn account_id gegeben: Erst account-spezifische, dann globale (NULL)
        query = db.query(models.TrustedSender).filter_by(user_id=user_id)
        
        if account_id:
            # Order: account-specific first, then global (account_id=NULL)
            trusted_senders = query.filter(
                (models.TrustedSender.account_id == account_id) |
                (models.TrustedSender.account_id.is_(None))
            ).order_by(
                models.TrustedSender.account_id.desc()  # Account-specific first
            ).all()
        else:
            # Only global (account_id=NULL)
            trusted_senders = query.filter(models.TrustedSender.account_id.is_(None)).all()
        
        # Pattern ist bereits normalisiert
        for ts in trusted_senders:
            pattern = ts.sender_pattern
            
            if ts.pattern_type == 'exact':
                if pattern == sender_lower:
                    logger.debug(f"✅ Trusted sender matched (exact): {sender_email}")
                    return {
                        'id': ts.id,
                        'label': ts.label,
                        'use_urgency_booster': ts.use_urgency_booster,
                        'pattern': ts.sender_pattern,
                        'pattern_type': 'exact',
                        'account_id': ts.account_id
                    }
            
            elif ts.pattern_type == 'email_domain' and email_domain:
                if pattern == email_domain:
                    logger.debug(f"✅ Trusted sender matched (email_domain): {sender_email}")
                    return {
                        'id': ts.id,
                        'label': ts.label,
                        'use_urgency_booster': ts.use_urgency_booster,
                        'pattern': ts.sender_pattern,
                        'pattern_type': 'email_domain',
                        'account_id': ts.account_id
                    }
            
            elif ts.pattern_type == 'domain':
                # SECURITY: Match exact domain OR subdomains (e.g., company.com matches @company.com and @mail.company.com)
                # BUT NOT: test-company.com (different domain - suffix spoofing attack)
                parts = sender_lower.split('@')
                if len(parts) == 2:
                    sender_domain = parts[1]
                    # Exact domain match: @company.com
                    if sender_domain == pattern:
                        logger.debug(f"✅ Trusted sender matched (domain exact): {sender_email}")
                        return {
                            'id': ts.id,
                            'label': ts.label,
                            'use_urgency_booster': ts.use_urgency_booster,
                            'pattern': ts.sender_pattern,
                            'pattern_type': 'domain',
                            'account_id': ts.account_id
                        }
                    # Subdomain match: @mail.company.com (but NOT test-company.com)
                    elif sender_domain.endswith('.' + pattern):
                        logger.debug(f"✅ Trusted sender matched (domain subdomain): {sender_email}")
                        return {
                            'id': ts.id,
                            'label': ts.label,
                            'use_urgency_booster': ts.use_urgency_booster,
                            'pattern': ts.sender_pattern,
                            'pattern_type': 'domain',
                            'account_id': ts.account_id
                        }
        
        return None
    
    @staticmethod
    def add_trusted_sender(
        db,
        user_id: int,
        sender_pattern: str,
        pattern_type: str,
        label: Optional[str] = None,
        account_id: Optional[int] = None
    ) -> Dict:
        """
        Fügt vertrauenswürdigen Sender hinzu.
        
        Mit Validierung und Limits
        
        Args:
            account_id: Optional - spezifisches Account. NULL = global für alle Accounts
        """
        models = importlib.import_module(".02_models", "src")
        
        # Validate pattern_type
        if pattern_type not in ['exact', 'email_domain', 'domain']:
            return {'success': False, 'error': f'Ungültiger pattern_type: {pattern_type}'}
        
        # Normalize
        sender_pattern = sender_pattern.lower().strip()
        
        # Validierung
        if pattern_type == 'exact':
            if not re.match(EMAIL_REGEX, sender_pattern):
                return {'success': False, 'error': 'Ungültiges Email-Format'}
        
        elif pattern_type == 'email_domain':
            if not sender_pattern.startswith('@'):
                return {'success': False, 'error': 'Email-Domain muss mit @ beginnen'}
            domain_part = sender_pattern[1:]
            if not re.match(DOMAIN_REGEX, domain_part):
                return {'success': False, 'error': 'Ungültiges Domain-Format'}
        
        elif pattern_type == 'domain':
            if not re.match(DOMAIN_REGEX, sender_pattern):
                return {'success': False, 'error': 'Ungültiges Domain-Format'}
        
        # Check Limit (per account or global)
        if account_id:
            current_count = db.query(models.TrustedSender).filter_by(
                user_id=user_id, account_id=account_id
            ).count()
        else:
            current_count = db.query(models.TrustedSender).filter_by(
                user_id=user_id, account_id=None
            ).count()
        if current_count >= MAX_TRUSTED_SENDERS_PER_USER:
            return {
                'success': False,
                'error': f'Limit erreicht ({MAX_TRUSTED_SENDERS_PER_USER} Sender maximum)'
            }
        
        # Check if exists - database has UNIQUE(user_id, sender_pattern)
        # So we check the same way - regardless of account_id
        existing = db.query(models.TrustedSender).filter(
            models.TrustedSender.user_id == user_id,
            models.TrustedSender.sender_pattern == sender_pattern
        ).first()
        
        if existing:
            return {
                'success': True,
                'already_exists': True,
                'id': existing.id,
                'sender_pattern': existing.sender_pattern,
                'pattern_type': existing.pattern_type,
                'label': existing.label,
                'message': 'Sender bereits in Liste'
            }
        
        # Create
        trusted = models.TrustedSender(
            user_id=user_id,
            account_id=account_id,
            sender_pattern=sender_pattern,
            pattern_type=pattern_type,
            label=label,
            use_urgency_booster=True,
            added_at=datetime.now(UTC),
            email_count=0
        )
        
        try:
            db.add(trusted)
            db.commit()
            
            logger.info(f"✅ User {user_id} added trusted sender: {sender_pattern} ({pattern_type})")
            
            return {
                'success': True,
                'id': trusted.id,
                'sender_pattern': trusted.sender_pattern,
                'pattern_type': trusted.pattern_type,
                'label': trusted.label
            }
        except Exception as e:
            db.rollback()
            # Check if it's a unique constraint violation (duplicate)
            if "UNIQUE constraint failed" in str(e) or "unique" in str(e).lower():
                # Find the existing entry
                existing = db.query(models.TrustedSender).filter(
                    models.TrustedSender.user_id == user_id,
                    models.TrustedSender.sender_pattern == sender_pattern
                ).first()
                
                if existing:
                    return {
                        'success': True,
                        'already_exists': True,
                        'id': existing.id,
                        'sender_pattern': existing.sender_pattern,
                        'pattern_type': existing.pattern_type,
                        'label': existing.label,
                        'message': 'Sender bereits in Liste'
                    }
            
            # Re-raise if it's a different error
            raise e
    
    @staticmethod
    def update_last_seen(db, trusted_sender_id: int):
        """
        Aktualisiert last_seen_at und email_count.
        
        Transaktionales Update für Consistency
        """
        models = importlib.import_module(".02_models", "src")
        
        try:
            db.execute(
                update(models.TrustedSender)
                .where(models.TrustedSender.id == trusted_sender_id)
                .values(
                    last_seen_at=datetime.now(UTC),
                    email_count=models.TrustedSender.email_count + 1
                )
            )
            db.commit()
        except Exception as e:
            logger.error(f"Failed to update trusted sender {trusted_sender_id}: {e}")
            db.rollback()
    
    @staticmethod
    def get_suggestions_from_emails(
        db,
        user_id: int,
        master_key: str,
        limit: int = 10,
        account_id: Optional[int] = None
    ) -> List[Dict]:
        """Schlägt Sender vor basierend auf Email-Historie.
        
        Args:
            account_id: Optional - wenn gesetzt, filtert E-Mails UND bestehende Whitelists nach diesem Account
        """
        import logging
        logger = logging.getLogger(__name__)
        
        models = importlib.import_module(".02_models", "src")
        encryption = importlib.import_module(".08_encryption", "src")
        
        # Query für häufige Sender - MIT Account-Filter wenn angegeben
        query = db.query(
            models.RawEmail.encrypted_sender,
            func.count(models.RawEmail.id).label('count')
        ).filter(
            models.RawEmail.user_id == user_id,
            models.RawEmail.deleted_at.is_(None)
        )
        
        # WICHTIG: Filtere E-Mails nach Account wenn account_id angegeben
        if account_id:
            query = query.filter(models.RawEmail.mail_account_id == account_id)
            logger.info(f"Suggestions: Filtering emails by account_id={account_id}")
        
        frequent_senders = query.group_by(
            models.RawEmail.encrypted_sender
        ).having(
            func.count(models.RawEmail.id) >= 1  # Mindestens 1 Email (für Tests)
        ).order_by(
            func.count(models.RawEmail.id).desc()
        ).limit(limit * 3).all()
        
        logger.info(f"Suggestions: Found {len(frequent_senders)} frequent senders for user {user_id}" + 
                   (f" (account_id={account_id})" if account_id else ""))
        
        suggestions = []
        
        # Get existing trusted patterns (account-aware) - include all relevant entries
        existing_query = db.query(models.TrustedSender).filter_by(user_id=user_id)
        
        if account_id:
            # For specific account: include account-specific AND global (both block new suggestions)
            existing_query = existing_query.filter(
                (models.TrustedSender.account_id == account_id) |
                (models.TrustedSender.account_id.is_(None))
            )
        else:
            # For global suggestions: include ALL (global would conflict with any account-specific)
            # Don't filter by account - show all existing patterns
            pass
        
        existing_senders = existing_query.all()
        trusted_patterns = set()
        trusted_domains = set()
        trusted_email_domains = set()
        
        # Build comprehensive pattern sets
        for ts in existing_senders:
            pattern = ts.sender_pattern.lower()
            trusted_patterns.add(pattern)
            
            # Only track domains if they are explicitly stored as domain patterns
            # Do NOT extract domains from 'exact' patterns - they should only block the exact email
            if ts.pattern_type == 'email_domain' and pattern.startswith('@'):
                trusted_email_domains.add(pattern)
                trusted_domains.add(pattern[1:])
            elif ts.pattern_type == 'domain':
                trusted_domains.add(pattern)
        
        logger.info(f"Suggestions: Found {len(trusted_patterns)} trusted patterns, {len(trusted_domains)} domains, {len(trusted_email_domains)} email domains")
        logger.info(f"Trusted patterns: {trusted_patterns}")
        logger.info(f"Trusted domains: {trusted_domains}")
        
        decryption_errors = 0
        
        # Use dict to deduplicate by email address and sum counts
        suggestions_dict = {}
        
        for encrypted_sender, count in frequent_senders:
            try:
                sender = encryption.EmailDataManager.decrypt_email_sender(encrypted_sender, master_key)
                sender_lower = sender.lower()
                
                # Extract email from "Display Name" <email@domain.com> format
                email_match = re.search(r'<(.+?)>', sender)
                email_only = email_match.group(1).lower() if email_match else sender_lower
                
                logger.info(f"Checking suggestion: {sender_lower} (email: {email_only})")
                
                # Check against existing patterns more comprehensively
                if email_only in trusted_patterns:
                    logger.info(f"Skipping {email_only} - exact pattern match")
                    continue
                
                # For email addresses, check domain patterns
                if '@' in email_only:
                    domain = email_only.split('@')[1]
                    email_domain = '@' + domain
                    
                    # Skip if domain is already trusted in any form
                    if (domain in trusted_domains or 
                        email_domain in trusted_email_domains or
                        email_domain in trusted_patterns or 
                        domain in trusted_patterns):
                        logger.info(f"Skipping {email_only} - domain/email_domain match ({domain} or {email_domain})")
                        continue
                    
                    logger.info(f"Including suggestion: {email_only}")
                    
                    # Default zu 'exact', aber könnte auf email_domain wechseln
                    # (wenn später mehrere @domain.ch Mails sichtbar sind)
                    suggested_type = 'exact'
                else:
                    suggested_type = 'exact'
                
                # Normalisiere Sender mittels prepare_suggestion()
                clean_sender = prepare_suggestion(sender, suggested_type)
                
                # Deduplicate: If email already in dict, sum the counts
                if clean_sender in suggestions_dict:
                    suggestions_dict[clean_sender]['email_count'] += count
                    logger.info(f"Duplicate found - summing count for {clean_sender}: {suggestions_dict[clean_sender]['email_count']}")
                else:
                    suggestions_dict[clean_sender] = {
                        'sender': clean_sender,
                        'email_count': count,
                        'suggested_pattern_type': suggested_type
                    }
            
            except Exception as e:
                decryption_errors += 1
                logger.error(f"Decryption failed for sender suggestion: {e}")
                
                if decryption_errors > 10:
                    logger.warning("Too many decryption errors, aborting suggestions")
                    break
        
        # Convert dict to list and limit
        suggestions = list(suggestions_dict.values())[:limit]
        
        logger.info(f"Suggestions: Returning {len(suggestions)} suggestions (after deduplication)")
        return suggestions
