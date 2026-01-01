#!/usr/bin/env python3
import re

with open('src/06_mail_fetcher.py', 'r') as f:
    content = f.read()

# Finde und ersetze die fetch_new_emails() Methode (von "if not self.connection:" bis "return []")
# Das ist ein großer Block, daher nutzen wir Regex mit MULTILINE und DOTALL

pattern = r'(    def fetch_new_emails\(.*?\) -> List\[Dict\]:.*?)(        if not self\.connection:.*?return \[\])'

new_body = r'''        if not self.connection:
            self.connect()

        try:
            conn = self.connection
            if conn is None:
                raise ConnectionError("IMAP connection failed")
            
            # Phase 14b: IMAPClient gibt UIDVALIDITY direkt zurück!
            folder_info = conn.select_folder(folder, readonly=True)
            if not folder_info:
                print(f"⚠️  Ordner {folder} nicht gefunden")
                return []
            
            # UIDVALIDITY aus folder_info Dict extrahieren
            server_uidvalidity = None
            try:
                uidval_raw = folder_info.get(b'UIDVALIDITY')
                if uidval_raw:
                    if isinstance(uidval_raw, list):
                        server_uidvalidity = int(uidval_raw[0]) if uidval_raw else None
                    else:
                        server_uidvalidity = int(uidval_raw)
            except (ValueError, TypeError, AttributeError) as e:
                logger.debug(f"Fehler beim Parsen von UIDVALIDITY: {e}")
            
            if not server_uidvalidity:
                logger.warning(f"⚠️  Konnte UIDVALIDITY für {folder} nicht abrufen!")
            
            # Phase 14b: UIDVALIDITY-Check
            if account_id and session and server_uidvalidity:
                from src import models_02 as models
                
                account = session.query(models.MailAccount).get(account_id)
                if account:
                    db_uidvalidity = account.get_uidvalidity(folder)
                    
                    if db_uidvalidity and db_uidvalidity != server_uidvalidity:
                        logger.warning(
                            f"⚠️  UIDVALIDITY CHANGED: {folder} "
                            f"(DB: {db_uidvalidity} → Server: {server_uidvalidity})"
                        )
                        self._invalidate_folder(session, account_id, folder)
                    
                    account.set_uidvalidity(folder, server_uidvalidity)
                    session.commit()
            
            self._current_folder_uidvalidity = server_uidvalidity

            # Phase 13C Part 4 & 2: Build IMAP SEARCH criteria
            search_criteria = []
            
            if uid_range:
                try:
                    start_uid = int(uid_range.split(':')[0])
                    mail_ids = conn.search(f"UID {start_uid}:*")
                except Exception as e:
                    logger.debug(f"Fehler beim UID-Range Search: {e}")
                    mail_ids = []
            else:
                if unseen_only:
                    search_criteria.append("UNSEEN")
                
                if flagged_only:
                    search_criteria.append("FLAGGED")
                
                if since:
                    date_str = since.strftime("%d-%b-%Y")
                    search_criteria.append(f"SINCE {date_str}")
                
                if before:
                    date_str = before.strftime("%d-%b-%Y")
                    search_criteria.append(f"BEFORE {date_str}")
                
                search_string = " ".join(search_criteria) if search_criteria else "ALL"
                
                try:
                    mail_ids = conn.search(search_string)
                except Exception as e:
                    logger.debug(f"Fehler beim SEARCH: {e}")
                    mail_ids = []
                
                if search_criteria:
                    print(f"🔍 Filter: {search_string}")

            if not mail_ids:
                if uid_range:
                    print(f"📧 0 Mails gefunden (keine neuen seit UID {uid_range.split(':')[0]})")
                else:
                    print("📧 0 Mails gefunden")
                return []
            
            mail_ids = sorted(mail_ids, reverse=True)[:limit]
            print(f"📧 {len(mail_ids)} Mails gefunden")

            emails = []
            for mail_id in mail_ids:
                email_data = self._fetch_email_by_id(mail_id, folder)
                if email_data:
                    emails.append(email_data)

            if emails:
                self._calculate_thread_ids(emails)

            return emails

        except Exception as e:
            import traceback
            logger.error(f"❌ FETCH EXCEPTION: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            print(f"❌ Fehler beim Abrufen: {type(e).__name__}: {e}")
            return []'''

content = re.sub(
    r'(    def fetch_new_emails\(.*?\) -> List\[Dict\]:.*?""")(.*?)(        if not self\.connection:.*?return \[\])',
    r'\1' + new_body,
    content,
    flags=re.MULTILINE | re.DOTALL
)

with open('src/06_mail_fetcher.py', 'w') as f:
    f.write(content)

print("✅ fetch_new_emails() Body ersetzt!")
