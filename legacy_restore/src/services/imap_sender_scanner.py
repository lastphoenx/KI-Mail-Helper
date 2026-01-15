"""
IMAP Sender Scanner Service - Production-Ready Version
Scannt Mail-Accounts nach Absendern (nur Header) für Pre-Fetch Whitelist-Setup

Key Features:
- Timeout-Protection (max 1000 neueste Mails)
- Email-Normalisierung (Deduplizierung)
- Batch-Error-Recovery
- RFC 5322 compliant parsing
"""

import logging
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple
from imapclient import IMAPClient
from email.utils import parseaddr

logger = logging.getLogger(__name__)

# Konfiguration
MAX_EMAILS_TO_SCAN = 1000  # Verhindert Timeout bei großen Mailboxen
BATCH_SIZE = 500  # IMAP Fetch Batch Size für Performance
IMAP_TIMEOUT = 30  # Sekunden pro IMAP-Operation


def normalize_email(email_string: str) -> Tuple[str, str]:
    """
    Normalisiert Email-Adresse und extrahiert Namen.
    
    Verwendet email.utils.parseaddr für RFC 5322 compliant parsing.
    
    Examples:
        'John Doe <john@example.com>' -> ('john@example.com', 'John Doe')
        'JOHN@EXAMPLE.COM' -> ('john@example.com', '')
        '  john@example.com  ' -> ('john@example.com', '')
        '"Boss" <boss@firma.de>' -> ('boss@firma.de', 'Boss')
    
    Returns:
        Tuple[normalized_email (lowercase, trimmed), display_name]
    """
    # parseaddr ist RFC 5322 compliant und extrahiert Name + Email
    display_name, email = parseaddr(email_string)
    
    # Email normalisieren: lowercase + trim
    normalized_email = email.strip().lower()
    
    # Display name bereinigen
    display_name = display_name.strip()
    
    return (normalized_email, display_name)


def scan_account_senders(
    imap_server: str,
    imap_username: str,
    imap_password: str,
    folder: str = 'INBOX',
    limit: Optional[int] = None
) -> Dict:
    """
    Scannt Mail-Account nach Absendern ohne Full-Fetch (nur ENVELOPE Header).
    
    Production-Features:
        - Timeout-Protection (Limit auf neueste N Mails)
        - Batch-Error-Recovery (Continue bei Fehler)
        - Email-Normalisierung (Deduplizierung)
        - Finally-Block für Connection-Cleanup
        - RFC 5322 compliant parsing
    
    Args:
        imap_server: IMAP Server-Adresse (z.B. 'imap.gmail.com')
        imap_username: Login-Username
        imap_password: Login-Passwort
        folder: IMAP-Ordner (default: 'INBOX')
        limit: Max. Anzahl Mails zu scannen (default: 1000)
    
    Returns:
        {
            'success': bool,
            'senders': [
                {
                    'email': str,           # Normalisierte Email
                    'name': str,            # Display Name
                    'count': int,           # Anzahl Mails von diesem Absender
                    'suggested_type': str   # 'exact', 'email_domain', oder 'domain'
                },
                ...
            ],
            'total_senders': int,      # Anzahl unique Absender
            'total_emails': int,       # Total Emails im Ordner
            'scanned_emails': int,     # Tatsächlich gescannte Emails
            'limited': bool,           # True wenn nicht alle Mails gescannt
            'error': str               # Nur bei Fehler
        }
    """
    client = None
    
    try:
        # IMAP Connect mit Timeout
        logger.info(f"Connecting to {imap_server} as {imap_username} (folder: {folder})")
        
        client = IMAPClient(imap_server, use_uid=True, timeout=IMAP_TIMEOUT)
        client.login(imap_username, imap_password)
        
        # Ordner auswählen (read-only!)
        client.select_folder(folder, readonly=True)
        
        # Alle UIDs holen (neueste zuerst!)
        messages = client.search(['ALL'])
        if not messages:
            logger.info(f"No emails found in {folder}")
            return {
                'success': True,
                'senders': [],
                'total_senders': 0,
                'total_emails': 0,
                'scanned_emails': 0,
                'limited': False
            }
        
        # UIDs sortieren (neueste zuerst)
        messages = sorted(messages, reverse=True)
        
        total_emails = len(messages)
        logger.info(f"Found {total_emails} emails in {folder}")
        
        # Limit anwenden (Timeout-Protection)
        if limit is None:
            limit = MAX_EMAILS_TO_SCAN
        
        limited = total_emails > limit
        messages_to_scan = messages[:limit]
        scanned_count = len(messages_to_scan)
        
        if limited:
            logger.warning(f"Limiting scan to {limit} newest emails (total: {total_emails})")
        
        # Sender-Counter und Namen
        sender_counter = Counter()
        sender_names = {}  # email -> best_name
        
        # Batch-Fetch für Performance
        total_batches = (len(messages_to_scan) - 1) // BATCH_SIZE + 1
        
        for i in range(0, len(messages_to_scan), BATCH_SIZE):
            batch = messages_to_scan[i:i+BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            
            logger.info(f"Fetching batch {batch_num}/{total_batches} ({len(batch)} messages)")
            
            try:
                # Nur ENVELOPE holen (sehr schnell, kein Body!)
                response = client.fetch(batch, ['ENVELOPE'])
                
                for uid, data in response.items():
                    try:
                        envelope = data.get(b'ENVELOPE')
                        if not envelope or not envelope.from_:
                            continue
                        
                        # From-Field parsen (erstes Element ist der Absender)
                        from_field = envelope.from_[0]
                        
                        # Email-Adresse zusammenbauen
                        mailbox = from_field.mailbox.decode('utf-8', errors='ignore') if from_field.mailbox else 'unknown'
                        host = from_field.host.decode('utf-8', errors='ignore') if from_field.host else 'unknown'
                        raw_email = f"{mailbox}@{host}"
                        
                        # Name extrahieren
                        raw_name = from_field.name.decode('utf-8', errors='ignore') if from_field.name else ''
                        
                        # Normalisieren (RFC 5322 compliant)
                        # Format kann sein: '"Name" <email>' oder nur 'email'
                        full_from = f'"{raw_name}" <{raw_email}>' if raw_name else raw_email
                        normalized_email, display_name = normalize_email(full_from)
                        
                        # Skip ungültige Emails
                        if not normalized_email or '@' not in normalized_email:
                            continue
                        
                        # Counter aktualisieren
                        sender_counter[normalized_email] += 1
                        
                        # Namen speichern (bevorzuge nicht-leere Namen)
                        if display_name and (normalized_email not in sender_names or not sender_names.get(normalized_email)):
                            sender_names[normalized_email] = display_name
                        
                    except Exception as msg_error:
                        logger.warning(f"Error parsing message {uid}: {msg_error}")
                        # Continue mit nächster Message
                        continue
            
            except Exception as batch_error:
                logger.error(f"Batch {batch_num} failed: {batch_error}")
                # Continue mit nächstem Batch (nicht abbrechen!)
                continue
        
        # Ergebnis formatieren (sortiert nach Häufigkeit = "Top N")
        senders = []
        for email, count in sender_counter.most_common():
            # Pattern-Typ vorschlagen basierend auf Häufigkeit
            if count >= 5:
                # Viele Mails → Domain-Pattern vorschlagen
                suggested_type = 'domain'
            elif count >= 2:
                # Mehrere Mails → Email-Domain vorschlagen
                suggested_type = 'email_domain'
            else:
                # Einzelne Mail → Exact vorschlagen
                suggested_type = 'exact'
            
            senders.append({
                'email': email,
                'name': sender_names.get(email, ''),
                'count': count,
                'suggested_type': suggested_type
            })
        
        logger.info(f"Scan complete: {len(senders)} unique senders from {scanned_count} emails")
        
        return {
            'success': True,
            'senders': senders,
            'total_senders': len(senders),
            'total_emails': total_emails,
            'scanned_emails': scanned_count,
            'limited': limited
        }
        
    except Exception as e:
        logger.error(f"IMAP Scan Error: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'senders': [],
            'total_senders': 0,
            'total_emails': 0,
            'scanned_emails': 0,
            'limited': False
        }
    
    finally:
        # Immer Connection schließen
        if client:
            try:
                client.logout()
                logger.info("IMAP connection closed")
            except Exception as logout_error:
                logger.error(f"IMAP logout error: {logout_error}")
