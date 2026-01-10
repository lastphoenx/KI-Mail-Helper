"""
Test Envelope-Parsing gegen echte IMAP-Server (Phase 12 Vorbereitung)

Testet Datenextraktion für:
- Message-ID
- In-Reply-To
- To / CC / BCC
- Reply-To
- References
- Message-Size
- Content-Type
- Attachments

Gegen:
- GMX (Dovecot)
- Gmail (Google IMAP)
- Outlook (Microsoft IMAP)
"""

import os
import sys
import logging
from typing import Optional, Dict, List
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class EnvelopeExtractor:
    """Extrahiert erweiterte Envelope-Daten aus RFC822-Messages"""

    @staticmethod
    def extract_all(msg) -> Dict:
        """Extrahiert alle benötigten Metadaten aus einer Message"""
        return {
            'message_id': EnvelopeExtractor.extract_message_id(msg),
            'in_reply_to': EnvelopeExtractor.extract_in_reply_to(msg),
            'references': EnvelopeExtractor.extract_references(msg),
            'to': EnvelopeExtractor.extract_address_list(msg, 'To'),
            'cc': EnvelopeExtractor.extract_address_list(msg, 'Cc'),
            'bcc': EnvelopeExtractor.extract_address_list(msg, 'Bcc'),
            'reply_to': EnvelopeExtractor.extract_address_list(msg, 'Reply-To'),
            'message_size': EnvelopeExtractor.estimate_message_size(msg),
            'content_type': msg.get_content_type(),
            'charset': msg.get_content_charset() or 'utf-8',
            'has_attachments': EnvelopeExtractor.detect_attachments(msg),
        }

    @staticmethod
    def extract_message_id(msg) -> Optional[str]:
        """Extrahiert Message-ID (RFC 5322)"""
        msg_id = msg.get('Message-ID', '').strip()
        if msg_id:
            msg_id = msg_id.strip('<>')
            if '@' in msg_id:
                return msg_id
        return None

    @staticmethod
    def extract_in_reply_to(msg) -> Optional[str]:
        """Extrahiert In-Reply-To Header (RFC 5322)"""
        in_reply = msg.get('In-Reply-To', '').strip()
        if in_reply:
            in_reply = in_reply.strip('<>')
            if '@' in in_reply:
                return in_reply
        return None

    @staticmethod
    def extract_references(msg) -> Optional[str]:
        """Extrahiert References Header (RFC 5322)"""
        refs = msg.get('References', '').strip()
        if refs:
            return refs
        return None

    @staticmethod
    def extract_address_list(msg, header: str) -> Optional[str]:
        """Extrahiert Adressliste aus Header (To, Cc, Bcc, Reply-To)
        
        Returns: JSON string mit List von {name, email} dicts
        """
        try:
            import json
            from email.utils import parseaddr
            
            addresses_str = msg.get(header, '').strip()
            if not addresses_str:
                return None
            
            addresses = []
            for item in addresses_str.split(','):
                item = item.strip()
                if item:
                    name, email_addr = parseaddr(item)
                    if email_addr:
                        addresses.append({
                            'name': name.strip() or email_addr,
                            'email': email_addr.strip()
                        })
            
            return json.dumps(addresses) if addresses else None
        except Exception as e:
            logger.warning(f"Error parsing {header}: {e}")
            return None

    @staticmethod
    def estimate_message_size(msg) -> int:
        """Schätzt Nachrichtengröße in Bytes"""
        try:
            return len(msg.as_bytes())
        except:
            return 0

    @staticmethod
    def detect_attachments(msg) -> bool:
        """Prüft ob die Nachricht Anhänge enthält"""
        try:
            if not msg.is_multipart():
                return False
            
            for part in msg.walk():
                if part.get_content_disposition() == 'attachment':
                    filename = part.get_filename()
                    if filename:
                        return True
            return False
        except:
            return False


class TestEnvelopeParsing:
    """Testet Envelope-Parsing gegen echte IMAP-Server"""

    @staticmethod
    def test_gmx():
        """Test gegen GMX (Dovecot)"""
        print("\n" + "="*70)
        print("📧 Testing Envelope-Parsing gegen GMX (imap.gmx.net)")
        print("="*70)
        
        imap_server = os.getenv('IMAP_SERVER', '')
        imap_username = os.getenv('IMAP_USERNAME', '')
        imap_password = os.getenv('IMAP_PASSWORD', '')
        
        if not all([imap_server, imap_username, imap_password]):
            print("⚠️  Überspringe GMX-Test (keine Credentials in .env)")
            print("   Setze: IMAP_SERVER, IMAP_USERNAME, IMAP_PASSWORD")
            return
        
        TestEnvelopeParsing._test_server(
            name='GMX',
            server=imap_server,
            username=imap_username,
            password=imap_password,
            port=993
        )

    @staticmethod
    def _test_server(name: str, server: str, username: str, password: str, port: int = 993):
        """Generic Test gegen IMAP-Server"""
        import imaplib
        import email
        
        try:
            print(f"\n🔗 Verbinde zu {server}:{port} als {username}...")
            conn = imaplib.IMAP4_SSL(server, port)
            conn.login(username, password)
            print(f"✅ Verbunden")
            
            # Wähle INBOX
            status, mailbox_data = conn.select('INBOX', readonly=True)
            if status != 'OK':
                print(f"❌ Fehler beim Select: {status}")
                return
            
            # Hole die neuesten 5 Mails
            status, messages = conn.search(None, 'ALL')
            if status != 'OK':
                print("⚠️  Keine Mails gefunden")
                conn.close()
                return
            
            mail_ids = messages[0].split()
            print(f"📊 {len(mail_ids)} Mails in INBOX, teste die neuesten 3...")
            
            mail_ids = list(reversed(mail_ids))[:3]
            
            # Teste Envelope-Parsing
            results = []
            for i, mail_id in enumerate(mail_ids, 1):
                print(f"\n  📬 Mail #{i}/{len(mail_ids)} (UID: {mail_id.decode()})...")
                
                status, msg_data = conn.fetch(mail_id, '(RFC822 UID)')
                if status != 'OK':
                    print(f"    ❌ Fetch fehlgeschlagen")
                    continue
                
                try:
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    
                    # Extrahiere Envelope-Daten
                    envelope_data = EnvelopeExtractor.extract_all(msg)
                    
                    # Zeige Ergebnisse
                    print(f"    ✅ Envelope erfolgreich extrahiert:")
                    print(f"       Message-ID: {envelope_data['message_id'] or '(keine)'}")
                    print(f"       In-Reply-To: {envelope_data['in_reply_to'] or '(keine)'}")
                    print(f"       To: {envelope_data['to'][:50] if envelope_data['to'] else '(keine)'}...")
                    print(f"       Cc: {envelope_data['cc'][:50] if envelope_data['cc'] else '(keine)'}...")
                    print(f"       Reply-To: {envelope_data['reply_to'][:50] if envelope_data['reply_to'] else '(keine)'}...")
                    print(f"       Content-Type: {envelope_data['content_type']}")
                    print(f"       Size: {envelope_data['message_size']} bytes")
                    print(f"       Has Attachments: {envelope_data['has_attachments']}")
                    
                    results.append({
                        'uid': mail_id.decode(),
                        'data': envelope_data,
                        'status': 'OK'
                    })
                    
                except Exception as e:
                    print(f"    ❌ Parse-Fehler: {e}")
                    results.append({
                        'uid': mail_id.decode(),
                        'status': 'ERROR',
                        'error': str(e)
                    })
            
            # Statistik
            print(f"\n📈 Statistik:")
            ok_count = sum(1 for r in results if r['status'] == 'OK')
            error_count = sum(1 for r in results if r['status'] == 'ERROR')
            print(f"   ✅ {ok_count}/{len(results)} erfolgreich")
            print(f"   ❌ {error_count}/{len(results)} Fehler")
            
            # Message-ID Analyse
            msg_ids = [r['data']['message_id'] for r in results if r['status'] == 'OK' and r['data']['message_id']]
            print(f"\n📧 Message-ID Analyse:")
            print(f"   Vorhanden: {len(msg_ids)}/{ok_count}")
            if msg_ids:
                print(f"   Format: {msg_ids[0]}")
            
            # Thread-Info Analyse
            threading_data = [r for r in results if r['status'] == 'OK' and (r['data']['in_reply_to'] or r['data']['references'])]
            print(f"\n🔗 Threading-Daten:")
            print(f"   In-Reply-To: {sum(1 for r in results if r['status'] == 'OK' and r['data']['in_reply_to'])}/{ok_count}")
            print(f"   References: {sum(1 for r in results if r['status'] == 'OK' and r['data']['references'])}/{ok_count}")
            
            conn.close()
            print(f"\n✅ {name}-Test abgeschlossen")
            
        except Exception as e:
            print(f"❌ Fehler: {e}")
            logger.exception(f"Exception in {name} test:")


if __name__ == '__main__':
    print("\n🚀 Phase 12 Envelope-Parsing Test Suite")
    print("=" * 70)
    
    TestEnvelopeParsing.test_gmx()
    
    print("\n" + "="*70)
    print("✅ Test-Suite abgeschlossen")
    print("="*70)
