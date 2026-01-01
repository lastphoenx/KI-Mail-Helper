#!/usr/bin/env python3
import re

with open('src/06_mail_fetcher.py', 'r') as f:
    content = f.read()

# Ersetze die _fetch_email_by_id() Methode Signatur
old_sig = r'    def _fetch_email_by_id\(\s*self, mail_id: bytes, folder: str = "INBOX"\s*\) -> Optional\[Dict\]:'
new_sig = r'    def _fetch_email_by_id(self, mail_id: int, folder: str = "INBOX") -> Optional[Dict]:'

content = re.sub(old_sig, new_sig, content)

# Ersetze den Body der _fetch_email_by_id() Methode
# Das ist ein großer Block - wir müssen vom "try:" bis "return None" am Ende ersetzen

new_body = '''        """Holt eine einzelne E-Mail mit erweiterten Metadaten (Phase 12)
        
        Phase 14c: Nutzt IMAPClient für robustes Response-Handling
        - mail_id: Integer (IMAPClient gibt UIDs als int zurück)
        - Response: Dict statt (status, data) Tuple
        """
        try:
            if self.connection is None:
                return None
            conn = self.connection
            
            # IMAPClient: mail_id ist bereits int, kein Decoding nötig!
            mail_id_int = mail_id if isinstance(mail_id, int) else int(mail_id)
            
            # Phase 1: Metadaten ohne Body-Download
            # IMAPClient.fetch() gibt dict {uid: {b'RFC822': bytes, b'FLAGS': list, ...}}
            meta_response = conn.fetch(
                mail_id_int,
                ['BODYSTRUCTURE', 'RFC822.SIZE', 'FLAGS', 'BODY.PEEK[HEADER]']
            )
            
            if not meta_response or mail_id_int not in meta_response:
                return None
            
            meta = meta_response[mail_id_int]
            
            # Extrahiere Flags (IMAPClient gibt list von byte-Flags)
            flags_raw = meta.get(b'FLAGS', [])
            flags_str = [f.decode('ascii') if isinstance(f, bytes) else str(f) for f in flags_raw]
            flags_dict = self._parse_flags_dict(' '.join(flags_str))
            
            # Extrahiere UID (falls nicht schon bekannt)
            imap_uid = mail_id_int  # Wir wissen die UID schon!
            
            # RFC822.SIZE direktekt aus Meta
            message_size = None
            try:
                size_raw = meta.get(b'RFC822.SIZE')
                if size_raw:
                    message_size = int(size_raw) if isinstance(size_raw, (int, bytes)) else int(size_raw[0]) if isinstance(size_raw, list) else None
            except (ValueError, TypeError, AttributeError):
                pass
            
            # BODYSTRUCTURE parsen
            bodystructure_raw = meta.get(b'BODYSTRUCTURE')
            bodystructure_info = self._parse_bodystructure(bodystructure_raw) if bodystructure_raw else {}
            
            # Phase 2: Body laden (nur für Text-Extraktion)
            body_response = conn.fetch(mail_id_int, ['RFC822'])
            if not body_response or mail_id_int not in body_response:
                return None
            
            raw_email = body_response[mail_id_int].get(b'RFC822')
            if not raw_email:
                return None
                
            msg = email.message_from_bytes(raw_email)

            subject = self._decode_header(msg.get("Subject", ""))
            sender = self._decode_header(msg.get("From", ""))
            date_str = msg.get("Date", "")

            body = self._extract_body(msg)

            try:
                received_at = email.utils.parsedate_to_datetime(date_str)
            except Exception as e:
                logger.debug(f"Failed to parse date '{date_str}': {e}")
                received_at = datetime.now()

            # Envelope mit BODYSTRUCTURE-Daten anreichern (FINDING-002/003)
            envelope = self._parse_envelope(msg, bodystructure_info, message_size)

            # Phase 13C: Decode IMAP UTF-7 folder names to UTF-8
            folder_utf8 = decode_imap_folder_name(folder)
            
            # Phase 14b: UIDVALIDITY aus Closure (von fetch_new_emails gesetzt)
            uidvalidity = getattr(self, '_current_folder_uidvalidity', None)

            return {
                "uid": str(mail_id_int),  # Als String für Kompatibilität
                "sender": sender,
                "subject": subject,
                "body": body,
                "received_at": received_at,
                "imap_uid": imap_uid,
                "imap_folder": folder_utf8,  # UTF-8 decoded
                "imap_uidvalidity": uidvalidity,  # Phase 14b
                "imap_flags": ' '.join(flags_str),
                "message_id": envelope.get("message_id"),
                "in_reply_to": envelope.get("in_reply_to"),
                "to": envelope.get("to"),
                "cc": envelope.get("cc"),
                "bcc": envelope.get("bcc"),
                "reply_to": envelope.get("reply_to"),
                "references": envelope.get("references"),
                "message_size": envelope.get("message_size"),
                "content_type": envelope.get("content_type"),
                "charset": envelope.get("charset"),
                "has_attachments": envelope.get("has_attachments"),
                "imap_is_seen": flags_dict.get("imap_is_seen"),
                "imap_is_answered": flags_dict.get("imap_is_answered"),
                "imap_is_flagged": flags_dict.get("imap_is_flagged"),
                "imap_is_deleted": flags_dict.get("imap_is_deleted"),
                "imap_is_draft": flags_dict.get("imap_is_draft"),
                "thread_id": None,
                "parent_uid": None,
            }

        except Exception as e:
            logger.debug(
                f"Fetch mail error for ID {mail_id}: {e}"
            )
            print(
                f"⚠️  Fehler bei Mail-ID {mail_id}: "
                f"Abruf fehlgeschlagen"
            )
            return None'''

# Finde und ersetze den Body (von "try:" bis letztem "return None")
pattern = r'(    def _fetch_email_by_id\(self, mail_id: int, folder: str = "INBOX"\) -> Optional\[Dict\]:)\s*""".*?"""(.*?)(?=\n    def )'

replacement = r'\1' + new_body + r'\n'

content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)

with open('src/06_mail_fetcher.py', 'w') as f:
    f.write(content)

print("✅ _fetch_email_by_id() ersetzt!")
