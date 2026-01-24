"""
Auto-Action Rules Engine
========================

Automatische E-Mail-Verarbeitung basierend auf benutzerdefinierten Regeln.

Features:
- Conditional Matching (Sender, Subject, Body, Attachments, etc.)
- Actions (Move, Flag, Mark Read, Apply Tags, Set Priority)
- Priority-based Execution
- Statistics Tracking
- Dry-Run Mode für Testing

Usage:
    from src.auto_rules_engine import AutoRulesEngine
    
    engine = AutoRulesEngine(user_id=1, master_key="abc123", db_session=session)
    
    # Einzelne Email verarbeiten
    results = engine.process_email(email_id=456)
    
    # Neue Emails batch-verarbeiten
    stats = engine.process_new_emails(since_minutes=60)
"""

import re
import json
import logging
import importlib
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from sqlalchemy.orm import Session

# Import mit importlib wegen führender Zahl in Modulnamen
models = importlib.import_module(".02_models", "src")
encryption = importlib.import_module(".08_encryption", "src")

# Services
from src.services.tag_manager import TagManager

AutoRule = models.AutoRule
RawEmail = models.RawEmail
ProcessedEmail = models.ProcessedEmail
EmailTag = models.EmailTag
EmailTagAssignment = models.EmailTagAssignment
EmailDataManager = encryption.EmailDataManager

logger = logging.getLogger(__name__)


@dataclass
class RuleMatch:
    """Ergebnis eines Regel-Matchings"""
    rule: AutoRule
    matched: bool
    matched_conditions: List[str]  # Welche Bedingungen gematcht haben
    match_details: Dict[str, Any] = None  # Zusätzliche Debug-Info


@dataclass
class RuleExecutionResult:
    """Ergebnis einer Regel-Ausführung"""
    rule_id: int
    rule_name: str
    email_id: int
    success: bool
    actions_executed: List[str]
    error: Optional[str] = None


# ===== Vordefinierte Regel-Templates =====

RULE_TEMPLATES = {
    "newsletter_archive": {
        "name": "Newsletter automatisch archivieren",
        "description": "Verschiebt Newsletter in den Archiv-Ordner und markiert als gelesen",
        "priority": 50,
        "conditions": {
            "match_mode": "any",
            "sender_contains": "newsletter",
            "body_contains": "unsubscribe"
        },
        "actions": {
            "move_to_folder": "Archive",
            "mark_as_read": True,
            "apply_tag": "Newsletter"
        }
    },
    "spam_delete": {
        "name": "Spam-Keywords → Papierkorb",
        "description": "E-Mails mit Spam-Keywords direkt in den Papierkorb",
        "priority": 10,  # Hohe Priorität (niedrige Zahl)
        "conditions": {
            "match_mode": "any",
            "subject_contains": "[SPAM]",
            "subject_regex": r"(?i)(viagra|lottery|winner|prize|claim.*now)"
        },
        "actions": {
            "move_to_folder": "Trash",
            "mark_as_read": True,
            "stop_processing": True  # Keine weiteren Regeln ausführen
        }
    },
    "important_sender": {
        "name": "Wichtiger Absender → Als wichtig markieren",
        "description": "E-Mails von bestimmten Absendern als wichtig markieren",
        "priority": 20,
        "conditions": {
            "sender_domain": "example.com"
        },
        "actions": {
            "mark_as_flagged": True,
            "apply_tag": "Wichtig"
        }
    },
    "attachment_archive": {
        "name": "E-Mails mit Anhängen → Archiv",
        "description": "Alle E-Mails mit Anhängen in Archiv-Ordner verschieben",
        "priority": 60,
        "conditions": {
            "has_attachment": True
        },
        "actions": {
            "move_to_folder": "Archive",
            "apply_tag": "Anhang"
        }
    }
}


class AutoRulesEngine:
    """
    Engine für automatische E-Mail-Aktionen basierend auf Regeln.
    
    Wird aufgerufen:
    1. Nach dem Fetch neuer E-Mails (Background-Job)
    2. Manuell vom User für bestehende E-Mails (/api/rules/apply)
    3. Beim Testen einer Regel (Dry-Run Mode)
    """
    
    def __init__(self, user_id: int, master_key: str, db_session: Session):
        """
        Args:
            user_id: User-ID
            master_key: Master-Key für Entschlüsselung
            db_session: DB-Session (required)
        """
        self.user_id = user_id
        self.master_key = master_key
        self._db_session = db_session
        self._mail_sync = None
    
    @property
    def db(self) -> Session:
        """DB-Session Accessor"""
        return self._db_session
    
    @property
    def mail_sync(self):
        """Lazy-Init für MailSynchronizer"""
        if self._mail_sync is None:
            mail_sync_module = importlib.import_module(".16_mail_sync", "src")
            self._mail_sync = mail_sync_module.MailSynchronizer(self.user_id, self.master_key)
        return self._mail_sync
    
    def get_active_rules(self) -> List[AutoRule]:
        """Lädt alle aktiven Regeln für den User, sortiert nach Priorität"""
        return self.db.query(AutoRule).filter_by(
            user_id=self.user_id,
            is_active=True
        ).order_by(AutoRule.priority.asc()).all()
    
    def process_email(
        self, 
        email_id: int,
        dry_run: bool = False,
        rule_id: Optional[int] = None
    ) -> List[RuleExecutionResult]:
        """
        Wendet Regeln auf eine E-Mail an.
        
        Args:
            email_id: ID der zu verarbeitenden E-Mail
            dry_run: Wenn True, nur prüfen ohne Aktionen auszuführen
            rule_id: Optional - Nur diese Regel testen (für Dry-Run)
            
        Returns:
            Liste der Ausführungsergebnisse
        """
        results = []
        
        # E-Mail laden
        raw_email = self.db.query(RawEmail).get(email_id)
        if not raw_email or raw_email.user_id != self.user_id:
            logger.warning(f"Email {email_id} nicht gefunden oder kein Zugriff")
            return results
        
        # E-Mail-Inhalte entschlüsseln
        email_data = self._decrypt_email_for_matching(raw_email)
        if not email_data:
            logger.error(f"Konnte Email {email_id} nicht entschlüsseln")
            return results
        
        # Regeln laden
        if rule_id:
            # Nur spezifische Regel testen
            rule = self.db.query(AutoRule).filter_by(
                id=rule_id, 
                user_id=self.user_id
            ).first()
            rules = [rule] if rule else []
        else:
            # Alle aktiven Regeln
            rules = self.get_active_rules()
        
        # Regeln anwenden
        for rule in rules:
            match = self._match_rule(rule, email_data)
            
            if match.matched:
                logger.info(
                    f"✅ Regel '{rule.name}' matched Email {email_id}: "
                    f"{match.matched_conditions}"
                )
                
                if dry_run:
                    # Dry-Run: Zeige was passieren würde
                    results.append(RuleExecutionResult(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        email_id=email_id,
                        success=True,
                        actions_executed=[
                            f"[DRY-RUN] Would execute: {json.dumps(rule.actions)}"
                        ]
                    ))
                else:
                    # Echte Ausführung
                    result = self._execute_rule(rule, raw_email, email_data)
                    results.append(result)
                
                # Stop-After-Match?
                if rule.actions.get('stop_processing', False):
                    logger.info(f"🛑 Regel '{rule.name}' hat stop_processing=True - stoppe weitere Regeln")
                    break
        
        return results
    
    def process_new_emails(
        self,
        since_minutes: int = 60,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Verarbeitet alle neuen E-Mails der letzten X Minuten.
        Wird typischerweise vom Background-Job aufgerufen.
        
        Args:
            since_minutes: Zeitfenster in Minuten
            limit: Max. Anzahl E-Mails
            
        Returns:
            Dict mit Statistiken
        """
        # PHASE 27: Neue E-Mails finden basierend auf processing_status
        # Filtere nach:
        # - AI-Klassifizierung abgeschlossen (status >= 40)
        # - Noch nicht von Auto-Rules verarbeitet (status < 50)
        # - Nicht in Fehler-Status (status >= 0)
        # HINWEIS: Kein created_at-Filter! Status ist robuster (vermeidet Missing bei Resume/Long-Sync)
        new_emails = self.db.query(RawEmail).filter(
            RawEmail.user_id == self.user_id,
            RawEmail.processing_status >= models.EmailProcessingStatus.AI_CLASSIFIED,  # Status 40+
            RawEmail.processing_status < models.EmailProcessingStatus.AUTO_RULES_APPLIED,  # Status < 50
            RawEmail.processing_status >= 0,  # Keine Fehler-Stati
            RawEmail.deleted_at == None
        ).limit(limit).all()
        
        stats = {
            "emails_checked": len(new_emails),
            "rules_triggered": 0,
            "actions_executed": 0,
            "errors": 0,
            "processed_email_ids": []
        }
        
        for email in new_emails:
            try:
                results = self.process_email(email.id, dry_run=False)
                
                has_error = False
                for result in results:
                    if result.success:
                        stats["rules_triggered"] += 1
                        stats["actions_executed"] += len(result.actions_executed)
                    else:
                        stats["errors"] += 1
                        has_error = True
                
                # Nur bei Erfolg als verarbeitet markieren
                if not has_error:
                    email.auto_rules_processed = True
                    
                    # Phase 27: Status-Update nach Auto-Rules
                    # WICHTIG: Erst auf AUTO_RULES_APPLIED setzen (Status 50)
                    email.processing_status = models.EmailProcessingStatus.AUTO_RULES_APPLIED
                    email.processing_last_attempt_at = datetime.now(UTC)
                    self.db.flush()  # Zwischenspeichern (crash-safe)

                    # Dann auf COMPLETE setzen (Status 100) - Rules waren letzter Schritt
                    # HINWEIS: Kein flush() nötig - wird mit batch-commit() persistent
                    email.processing_status = models.EmailProcessingStatus.COMPLETE
                    email.processing_last_attempt_at = datetime.now(UTC)
                    
                    stats["processed_email_ids"].append(email.id)
                
            except Exception as e:
                logger.error(f"Auto-Rule Error für E-Mail {email.id}: {e}")
                stats["errors"] += 1
                
                # Phase 27: Status auf Fehler setzen
                try:
                    email.processing_status = models.EmailProcessingStatus.AUTO_RULES_FAILED
                    email.processing_error = str(e)[:1000]
                    email.processing_last_attempt_at = datetime.now(UTC)
                    self.db.flush()
                except Exception:
                    pass  # Falls Status-Update fehlschlägt, ignorieren
                
                # NICHT als processed markieren → wird beim nächsten Run erneut versucht
        
        # Commit batch
        if stats["processed_email_ids"]:
            self.db.commit()
            logger.info(
                f"✅ Auto-Rules: {stats['rules_triggered']} Regeln auf "
                f"{len(stats['processed_email_ids'])} E-Mails angewendet"
            )
        
        return stats
    
    def _decrypt_email_for_matching(self, raw_email: RawEmail) -> Optional[Dict]:
        """Entschlüsselt E-Mail-Felder für Regel-Matching"""
        try:
            # Hole ProcessedEmail ID f\u00fcr Tag-Checks
            processed_email = self.db.query(ProcessedEmail).filter_by(
                raw_email_id=raw_email.id
            ).first()
            
            return {
                'email_id': processed_email.id if processed_email else None,
                'sender': EmailDataManager.decrypt_email_sender(
                    raw_email.encrypted_sender or "", self.master_key
                ) or '',
                'subject': EmailDataManager.decrypt_email_subject(
                    raw_email.encrypted_subject or "", self.master_key
                ) or '',
                'body': EmailDataManager.decrypt_email_body(
                    raw_email.encrypted_body or "", self.master_key
                ) or '',
                'has_attachment': raw_email.has_attachments or False,
                'folder': raw_email.imap_folder or '',
                'flags': raw_email.imap_flags or '',
                'is_seen': raw_email.imap_is_seen or False,
                'is_flagged': raw_email.imap_is_flagged or False
            }
        except Exception as e:
            logger.error(f"Entschlüsselung für Regel-Matching fehlgeschlagen: {e}")
            return None
    
    def _match_rule(self, rule: AutoRule, email_data: Dict) -> RuleMatch:
        """
        Pr\u00fcft ob eine Regel auf die E-Mail-Daten matched.
        
        Unterst\u00fctzte Bedingungen:
        - match_mode: "all" (AND) oder "any" (OR)
        - sender_equals: Exakte \u00dcbereinstimmung
        - sender_contains: Teil-String
        - sender_not_contains: Negativ-Match (darf NICHT enthalten)
        - sender_domain: Domain-Teil (@example.com)
        - subject_equals: Exakte \u00dcbereinstimmung
        - subject_contains: Teil-String im Betreff
        - subject_not_contains: Negativ-Match
        - subject_regex: Regex-Match im Betreff
        - body_contains: Teil-String im Body
        - body_not_contains: Negativ-Match
        - body_regex: Regex-Match im Body
        - has_attachment: true/false
        - folder_equals: Exakter Ordner-Name
        - has_tag: Email hat bereits dieses Tag (f\u00fcr Regel-Ketten)
        - not_has_tag: Email hat dieses Tag NICHT
        - ai_suggested_tag: KI schl\u00e4gt dieses Tag vor (Phase F.2 Integration)
        - ai_confidence_threshold: Min. Confidence in % (50-100) f\u00fcr ai_suggested_tag
        """
        conditions = rule.conditions
        match_mode = conditions.get('match_mode', 'all')  # 'all' (AND) oder 'any' (OR)
        
        matched_conditions = []
        match_details = {}
        
        # Sender-Bedingungen
        if 'sender_equals' in conditions:
            if email_data['sender'].lower() == conditions['sender_equals'].lower():
                matched_conditions.append('sender_equals')
                match_details['sender_equals'] = email_data['sender']
        
        if 'sender_contains' in conditions:
            if conditions['sender_contains'].lower() in email_data['sender'].lower():
                matched_conditions.append('sender_contains')
                match_details['sender_contains'] = email_data['sender']
        
        if 'sender_not_contains' in conditions:
            if conditions['sender_not_contains'].lower() not in email_data['sender'].lower():
                matched_conditions.append('sender_not_contains')
                match_details['sender_not_contains'] = f"Nicht enthalten: {conditions['sender_not_contains']}"
        
        if 'sender_domain' in conditions:
            sender_domain = email_data['sender'].split('@')[-1].lower() if '@' in email_data['sender'] else ''
            if sender_domain == conditions['sender_domain'].lower():
                matched_conditions.append('sender_domain')
                match_details['sender_domain'] = sender_domain
        
        # Subject-Bedingungen
        if 'subject_equals' in conditions:
            if email_data['subject'].lower() == conditions['subject_equals'].lower():
                matched_conditions.append('subject_equals')
                match_details['subject_equals'] = email_data['subject'][:50]
        
        if 'subject_contains' in conditions:
            if conditions['subject_contains'].lower() in email_data['subject'].lower():
                matched_conditions.append('subject_contains')
                match_details['subject_contains'] = email_data['subject'][:50]
        
        if 'subject_not_contains' in conditions:
            if conditions['subject_not_contains'].lower() not in email_data['subject'].lower():
                matched_conditions.append('subject_not_contains')
                match_details['subject_not_contains'] = f"Nicht enthalten: {conditions['subject_not_contains']}"
        
        if 'subject_regex' in conditions:
            try:
                if re.search(conditions['subject_regex'], email_data['subject'], re.IGNORECASE):
                    matched_conditions.append('subject_regex')
                    match_details['subject_regex'] = email_data['subject'][:50]
            except re.error as e:
                logger.warning(f"Ungültiger Regex in Regel {rule.id}: {conditions['subject_regex']} - {e}")
                match_details['subject_regex_error'] = f"Ungültiger Regex: {str(e)}"
        
        # Body-Bedingungen
        if 'body_contains' in conditions:
            if conditions['body_contains'].lower() in email_data['body'].lower():
                matched_conditions.append('body_contains')
                match_details['body_contains'] = True
        
        if 'body_not_contains' in conditions:
            if conditions['body_not_contains'].lower() not in email_data['body'].lower():
                matched_conditions.append('body_not_contains')
                match_details['body_not_contains'] = f"Nicht enthalten: {conditions['body_not_contains']}"
        
        if 'body_regex' in conditions:
            try:
                if re.search(conditions['body_regex'], email_data['body'], re.IGNORECASE):
                    matched_conditions.append('body_regex')
                    match_details['body_regex'] = True
            except re.error as e:
                logger.warning(f"Ungültiger Body-Regex in Regel {rule.id}: {conditions['body_regex']} - {e}")
                match_details['body_regex_error'] = f"Ungültiger Regex: {str(e)}"
        
        # Attachment-Bedingung
        if 'has_attachment' in conditions:
            if email_data['has_attachment'] == conditions['has_attachment']:
                matched_conditions.append('has_attachment')
                match_details['has_attachment'] = email_data['has_attachment']
        
        # Ordner-Bedingung
        if 'folder_equals' in conditions:
            if email_data['folder'] == conditions['folder_equals']:
                matched_conditions.append('folder_equals')
                match_details['folder_equals'] = email_data['folder']
        
        # Tag-Bedingungen (neu - Phase G.2 Enhancement)
        if 'has_tag' in conditions:
            # Prüfe ob Email bereits ein bestimmtes Tag hat
            tag_name = conditions['has_tag']
            if self._email_has_tag(email_data['email_id'], tag_name):
                matched_conditions.append('has_tag')
                match_details['has_tag'] = tag_name
        
        if 'not_has_tag' in conditions:
            # Prüfe ob Email ein Tag NICHT hat
            tag_name = conditions['not_has_tag']
            if not self._email_has_tag(email_data['email_id'], tag_name):
                matched_conditions.append('not_has_tag')
                match_details['not_has_tag'] = f"Hat Tag NICHT: {tag_name}"
        
        # KI-Suggested-Tag (neu - Phase G.2 mit Phase F.2 Integration)
        if 'ai_suggested_tag' in conditions:
            target_tag = conditions['ai_suggested_tag']
            threshold = conditions.get('ai_confidence_threshold', 85)
            
            # Hole KI-Vorschlag für diese Email
            suggested = self._get_ai_suggested_tag(email_data['email_id'], target_tag, threshold)
            if suggested:
                matched_conditions.append('ai_suggested_tag')
                match_details['ai_suggested_tag'] = f"{target_tag} (Confidence: {suggested['confidence']}%)"
        
        # Match-Logik auswerten
        total_conditions = len([k for k in conditions.keys() if k != 'match_mode'])
        
        if total_conditions == 0:
            matched = False  # Keine Bedingungen = Kein Match
        elif match_mode == 'any':
            matched = len(matched_conditions) > 0
        else:  # 'all'
            matched = len(matched_conditions) == total_conditions
        
        return RuleMatch(
            rule=rule,
            matched=matched,
            matched_conditions=matched_conditions,
            match_details=match_details
        )
    
    def _execute_rule(
        self, 
        rule: AutoRule, 
        raw_email: RawEmail,
        email_data: Dict
    ) -> RuleExecutionResult:
        """
        Führt die Aktionen einer gematchten Regel aus.
        
        Unterstützte Aktionen:
        - move_to_folder: Verschieben in IMAP-Ordner
        - mark_as_read: Als gelesen markieren
        - mark_as_flagged: Als wichtig markieren
        - apply_tag: Tag zuweisen (lokal in DB)
        - set_priority: Priorität setzen (low/high)
        - delete: In Papierkorb verschieben
        """
        actions = rule.actions
        executed = []
        error = None
        
        try:
            # Action: Move to Folder
            if 'move_to_folder' in actions:
                target_folder = actions['move_to_folder']
                try:
                    result = self.mail_sync.move_email(
                        uid=raw_email.imap_uid,
                        source_folder=raw_email.imap_folder,
                        target_folder=target_folder
                    )
                    if result.success:
                        # DB aktualisieren
                        raw_email.imap_folder = result.target_folder
                        raw_email.imap_uid = result.target_uid
                        raw_email.imap_uidvalidity = result.target_uidvalidity
                        executed.append(f"move_to:{target_folder}")
                        logger.info(f"📁 Moved email {raw_email.id} to {target_folder}")
                except Exception as move_err:
                    logger.error(f"Move failed: {move_err}")
                    executed.append(f"move_to:{target_folder} [FAILED]")
            
            # Action: Mark as Read
            if actions.get('mark_as_read'):
                try:
                    success = self.mail_sync.mark_as_read(
                        uid=raw_email.imap_uid,
                        folder=raw_email.imap_folder
                    )
                    if success:
                        raw_email.imap_is_seen = True
                        executed.append("mark_as_read")
                        logger.info(f"✅ Marked email {raw_email.id} as read")
                except Exception as read_err:
                    logger.error(f"Mark as read failed: {read_err}")
            
            # Action: Mark as Flagged
            if actions.get('mark_as_flagged'):
                try:
                    success = self.mail_sync.add_flag(
                        uid=raw_email.imap_uid,
                        folder=raw_email.imap_folder,
                        flag='\\Flagged'
                    )
                    if success:
                        raw_email.imap_is_flagged = True
                        executed.append("mark_as_flagged")
                        logger.info(f"🚩 Flagged email {raw_email.id}")
                except Exception as flag_err:
                    logger.error(f"Mark as flagged failed: {flag_err}")
            
            # Action: Apply Tag (lokal in DB)
            # WICHTIG: email_tag_assignments.email_id referenziert processed_emails.id, NICHT raw_emails.id!
            if 'apply_tag' in actions:
                tag_name = actions['apply_tag']
                try:
                    # Erst ProcessedEmail finden - ohne diese kein Tag-Assignment möglich
                    processed_email = self.db.query(ProcessedEmail).filter_by(
                        raw_email_id=raw_email.id
                    ).first()
                    
                    if not processed_email:
                        logger.warning(f"⚠️ Kann Tag '{tag_name}' nicht zuweisen - ProcessedEmail für raw_email {raw_email.id} existiert noch nicht")
                        executed.append(f"apply_tag:{tag_name} [SKIPPED - no ProcessedEmail]")
                    else:
                        # Prüfe ob Regel enable_learning aktiviert hat
                        should_learn = getattr(rule, 'enable_learning', False) if rule else False
                        
                        # Tag finden oder erstellen via TagManager
                        tag = self.db.query(EmailTag).filter_by(
                            user_id=self.user_id,
                            name=tag_name
                        ).first()
                        
                        if not tag:
                            # Tag erstellen mit optionaler Farbe aus actions
                            tag_color = actions.get('tag_color', '#6366F1')  # Default-Farbe
                            try:
                                tag = TagManager.create_tag(
                                    db=self.db,
                                    user_id=self.user_id,
                                    name=tag_name[:50],  # Max 50 Zeichen
                                    color=tag_color if tag_color.startswith('#') and len(tag_color) == 7 else '#6366F1'
                                )
                                logger.info(f"📝 Created new tag '{tag_name}' with color {tag_color}")
                            except ValueError as e:
                                # Tag existiert vielleicht schon (Race Condition) - nochmal holen
                                tag = self.db.query(EmailTag).filter_by(
                                    user_id=self.user_id,
                                    name=tag_name
                                ).first()
                                if not tag:
                                    logger.error(f"❌ Tag-Erstellung fehlgeschlagen: '{tag_name}': {e}")
                                    executed.append(f"apply_tag:{tag_name} [CREATE_FAILED]")
                                    tag = None  # Explizit auf None setzen
                        
                        # Tag zuweisen via TagManager (nur wenn tag erfolgreich gefunden/erstellt)
                        if tag:
                            # auto_assigned=True → kein Learning
                            # auto_assigned=False → Learning aktiv (wenn enable_learning=True in Regel)
                            success = TagManager.assign_tag(
                                db=self.db,
                                email_id=processed_email.id,
                                tag_id=tag.id,
                                user_id=self.user_id,
                                auto_assigned=not should_learn
                            )
                            
                            if success:
                                executed.append(f"apply_tag:{tag_name}")
                                logger.info(f"🏷️  Applied tag '{tag_name}' to email {raw_email.id} (processed_id={processed_email.id}, learning={'ON' if should_learn else 'OFF'})")
                            else:
                                executed.append(f"apply_tag:{tag_name} [ALREADY_EXISTS]")
                        
                except Exception as tag_err:
                    logger.error(f"Apply tag failed: {tag_err}")
            
            # Action: Set Priority (in ProcessedEmail)
            if 'set_priority' in actions:
                priority = actions['set_priority']
                try:
                    processed = self.db.query(ProcessedEmail).filter_by(
                        raw_email_id=raw_email.id
                    ).first()
                    
                    if processed:
                        if priority == 'low':
                            processed.dringlichkeit = 1
                            processed.wichtigkeit = 1
                            processed.farbe = 'grün'
                        elif priority == 'high':
                            processed.dringlichkeit = 3
                            processed.wichtigkeit = 3
                            processed.farbe = 'rot'
                        executed.append(f"set_priority:{priority}")
                        logger.info(f"⚡ Set priority '{priority}' for email {raw_email.id}")
                except Exception as prio_err:
                    logger.error(f"Set priority failed: {prio_err}")
            
            # Action: Delete (Soft-Delete)
            if actions.get('delete'):
                try:
                    raw_email.deleted_at = datetime.now(UTC)
                    executed.append("delete")
                    logger.info(f"🗑️  Soft-deleted email {raw_email.id}")
                except Exception as del_err:
                    logger.error(f"Delete failed: {del_err}")
            
            # Statistik aktualisieren
            rule.times_triggered += 1
            rule.last_triggered_at = datetime.now(UTC)
            
            # P2-004: Log successful execution
            processed_email = self.db.query(ProcessedEmail).filter_by(
                raw_email_id=raw_email.id
            ).first()
            
            if processed_email:
                # Extrahiere action_type für Log (erste Action oder "multiple")
                action_type = executed[0].split(':')[0] if executed else 'unknown'
                if len(executed) > 1:
                    action_type = 'multiple'
                
                log_entry = models.RuleExecutionLog(
                    user_id=self.user_id,
                    mail_account_id=raw_email.mail_account_id,
                    rule_id=rule.id,
                    processed_email_id=processed_email.id,
                    success=True,
                    error_message=None,
                    action_type=action_type
                )
                self.db.add(log_entry)
            
            self.db.commit()
            
            logger.info(
                f"✅ Regel '{rule.name}' ausgeführt für E-Mail {raw_email.id}: "
                f"{', '.join(executed)}"
            )
            
            return RuleExecutionResult(
                rule_id=rule.id,
                rule_name=rule.name,
                email_id=raw_email.id,
                success=True,
                actions_executed=executed
            )
            
        except Exception as e:
            self.db.rollback()
            error = str(e)
            logger.error(f"❌ Regel '{rule.name}' fehlgeschlagen: {e}")
            
            # P2-004: Log failed execution
            try:
                processed_email = self.db.query(ProcessedEmail).filter_by(
                    raw_email_id=raw_email.id
                ).first()
                
                if processed_email:
                    # Extrahiere action_type auch bei Fehler
                    action_type = executed[0].split(':')[0] if executed else 'unknown'
                    
                    log_entry = models.RuleExecutionLog(
                        user_id=self.user_id,
                        mail_account_id=raw_email.mail_account_id,
                        rule_id=rule.id,
                        processed_email_id=processed_email.id,
                        success=False,
                        error_message=error[:500],  # Limit error message length
                        action_type=action_type
                    )
                    self.db.add(log_entry)
                    self.db.commit()
            except Exception as log_err:
                logger.error(f"Failed to log rule execution error: {log_err}")
                # Don't fail the whole operation if logging fails
            
            return RuleExecutionResult(
                rule_id=rule.id,
                rule_name=rule.name,
                email_id=raw_email.id,
                success=False,
                actions_executed=executed,
                error=error
            )
    
    def _email_has_tag(self, email_id: int, tag_name: str) -> bool:
        """
        Pr\u00fcft ob eine Email ein bestimmtes Tag hat.
        
        Args:
            email_id: ProcessedEmail ID (nicht RawEmail!)
            tag_name: Name des Tags
            
        Returns:
            True wenn Email das Tag hat
        """
        try:
            # Finde Tag nach Name
            tag = self.db.query(EmailTag).filter_by(
                user_id=self.user_id,
                name=tag_name
            ).first()
            
            if not tag:
                return False
            
            # Prüfe ob Email-Tag-Assignment existiert
            assignment = self.db.query(EmailTagAssignment).filter_by(
                email_id=email_id,
                tag_id=tag.id
            ).first()
            
            return assignment is not None
            
        except Exception as e:
            logger.error(f"Fehler beim Prüfen von Tag '{tag_name}': {e}")
            return False
    
    def _get_ai_suggested_tag(
        self, 
        email_id: int, 
        target_tag: str, 
        threshold: int
    ) -> Optional[Dict[str, Any]]:
        """
        Holt KI-Tag-Vorschlag für Email und prüft ob es zum Target-Tag matched.
        
        Integriert Phase F.2 Smart Tag Suggestions.
        
        Args:
            email_id: ProcessedEmail ID
            target_tag: Gesuchtes Tag
            threshold: Min. Confidence in % (50-100)
            
        Returns:
            Dict mit {tag, confidence} wenn Match, sonst None
        """
        try:
            # Lazy import um zirkuläre Abhängigkeiten zu vermeiden
            try:
                smart_tags = importlib.import_module(".12_smart_tag_suggestions", "src")
            except ImportError:
                logger.warning("Phase F.2 Smart Tag Suggestions nicht verfügbar")
                return None
            
            # Hole Email
            email = self.db.query(ProcessedEmail).filter_by(id=email_id).first()
            if not email:
                return None
            
            # Hole KI-Vorschläge
            suggestions = smart_tags.get_tag_suggestions_for_email(
                db_session=self.db,
                email_id=email_id,
                user_id=self.user_id
            )
            
            if not suggestions:
                return None
            
            # Suche Target-Tag in Vorschl\u00e4gen
            for suggestion in suggestions:
                if suggestion['tag'].lower() == target_tag.lower():
                    confidence_pct = int(suggestion['confidence'] * 100)
                    
                    if confidence_pct >= threshold:
                        return {
                            'tag': suggestion['tag'],
                            'confidence': confidence_pct
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"Fehler beim Holen von AI-Tag-Vorschlag: {e}")
            return None


def create_rule_from_template(
    db_session: Session,
    user_id: int,
    template_name: str,
    overrides: Optional[Dict] = None
) -> Optional[AutoRule]:
    """
    Erstellt eine neue Regel aus einem Template.
    
    Args:
        db_session: DB-Session
        user_id: User-ID
        template_name: Name des Templates (z.B. 'newsletter_archive')
        overrides: Optionale Überschreibungen für conditions/actions
        
    Returns:
        Erstellte AutoRule oder None
    """
    if template_name not in RULE_TEMPLATES:
        logger.error(f"Unknown template: {template_name}")
        return None
    
    template = RULE_TEMPLATES[template_name].copy()
    
    # Apply overrides
    if overrides:
        if 'conditions' in overrides:
            template['conditions'].update(overrides['conditions'])
        if 'actions' in overrides:
            template['actions'].update(overrides['actions'])
        if 'name' in overrides:
            template['name'] = overrides['name']
        if 'priority' in overrides:
            template['priority'] = overrides['priority']
    
    # Create rule
    rule = AutoRule(
        user_id=user_id,
        name=template['name'],
        description=template.get('description'),
        priority=template.get('priority', 100),
        conditions=template['conditions'],
        actions=template['actions']
    )
    
    db_session.add(rule)
    db_session.commit()
    
    logger.info(f"✅ Created rule from template '{template_name}': {rule.name}")
    
    return rule
