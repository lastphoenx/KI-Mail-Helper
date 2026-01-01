#!/usr/bin/env python3
import sys, os, imaplib, email, re
from email.header import decode_header
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import src.02_models as models
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///emails.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)

def get_db_mails():
    s = Session()
    try:
        mails = s.query(models.RawEmail).filter(
            models.RawEmail.imap_folder == 'Archiv',
            models.RawEmail.user_id == 1
        ).order_by(models.RawEmail.imap_uid).all()
        return [{'uid': m.imap_uid, 'uidval': m.imap_uidvalidity} for m in mails]
    finally:
        s.close()

def get_imap_mails():
    s = Session()
    try:
        acc = s.query(models.MailAccount).filter(models.MailAccount.id == 1).first()
        # Credentials müssen manuell eingegeben werden für CLI
        server = input("IMAP Server (z.B. imap.gmx.net): ")
        user = input("Username: ")
        pw = input("Password: ")
    finally:
        s.close()
    
    print(f"Verbinde mit {server}...")
    c = imaplib.IMAP4_SSL(server, 993)
    c.login(user, pw)
    
    status, _ = c.select('Archiv', readonly=True)
    if status != 'OK':
        print("Archiv nicht gefunden!")
        return []
    
    # UIDVALIDITY
    uidval = None
    untagged = getattr(c, 'untagged_responses', {})
    if 'OK' in untagged:
        for r in untagged['OK']:
            s = r.decode() if isinstance(r, bytes) else str(r)
            m = re.search(r'UIDVALIDITY\s+(\d+)', s)
            if m:
                uidval = int(m.group(1))
                break
    
    print(f"UIDVALIDITY: {uidval}")
    
    # Search
    status, msgs = c.uid('search', None, 'ALL')
    if status != 'OK' or not msgs[0]:
        return []
    
    mail_ids = msgs[0].split()
    print(f"{len(mail_ids)} Mails gefunden")
    
    result = []
    for mid in mail_ids:
        mid_str = mid.decode() if isinstance(mid, bytes) else str(mid)
        status, data = c.uid('fetch', mid_str, '(RFC822.HEADER)')
        if status == 'OK' and data and data[0]:
            msg = email.message_from_bytes(data[0][1])
            subj = msg.get('Subject', '(no subject)')
            if subj.startswith('=?'):
                parts = decode_header(subj)
                subj = ''.join(
                    p.decode(e or 'utf-8', errors='replace') if isinstance(p, bytes) else str(p)
                    for p, e in parts
                )
            result.append({'uid': int(mid_str), 'uidval': uidval, 'subject': subj[:80]})
    
    c.logout()
    return result

print("=== Archiv Vergleich ===\n")
print("1. DB Mails:")
db = get_db_mails()
print(f"   {len(db)} Mails")
for m in db:
    print(f"   UID {m['uid']}, UIDVAL {m['uidval']}")

print("\n2. IMAP Mails:")
imap = get_imap_mails()
print(f"   {len(imap)} Mails\n")

print("=== IMAP Liste ===")
db_uids = {m['uid'] for m in db}
for m in imap:
    in_db = "✅" if m['uid'] in db_uids else "❌"
    print(f"{in_db} UID {m['uid']:<6} | {m['subject']}")

test = [m for m in imap if 'test' in m['subject'].lower() and 'verschieben' in m['subject'].lower()]
if test:
    print("\n🎯 Test-Mail gefunden:")
    for t in test:
        print(f"   UID {t['uid']}, in DB: {'✅' if t['uid'] in db_uids else '❌'}")
        print(f"   Subject: {t['subject']}")
