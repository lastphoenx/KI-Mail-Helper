#!/usr/bin/env python3

with open('src/06_mail_fetcher.py', 'r') as f:
    content = f.read()

old_text = """            # 3) Letzter Fallback: Ohne UIDVALIDITY weitermachen (suboptimal)
            if not server_uidvalidity:
                logger.warning(f"⚠️  Konnte UIDVALIDITY für {folder} nicht abrufen!")
                # Continue ohne UIDVALIDITY (Mails werden skipped in persistence)"""

new_text = """            # 3) Fallback: STATUS command (RFC 3501 - funktioniert überall!)
            if not server_uidvalidity:
                try:
                    status, status_resp = conn.status(folder, '(UIDVALIDITY)')
                    if status == 'OK' and status_resp:
                        resp_str = status_resp[0].decode('utf-8', errors='ignore') if isinstance(status_resp[0], bytes) else str(status_resp[0])
                        match = re.search(r'UIDVALIDITY\s+(\d+)', resp_str)
                        if match:
                            server_uidvalidity = int(match.group(1))
                            logger.debug(f"✅ UIDVALIDITY via STATUS: {server_uidvalidity}")
                except Exception as e:
                    logger.debug(f"STATUS fallback auch fehlgeschlagen: {e}")
            
            # 4) Letzter Fallback: Ohne UIDVALIDITY weitermachen (suboptimal)
            if not server_uidvalidity:
                logger.warning(f"⚠️  Konnte UIDVALIDITY für {folder} nicht abrufen!")
                # Continue ohne UIDVALIDITY (Mails werden skipped in persistence)"""

content = content.replace(old_text, new_text)

with open('src/06_mail_fetcher.py', 'w') as f:
    f.write(content)

print("✅ UIDVALIDITY-Extraction um STATUS-Fallback ergänzt!")
