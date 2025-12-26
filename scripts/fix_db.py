#!/usr/bin/env python3
"""
1. Setzt das kaputte IMAP-Passwort zurück
2. Aktualisiert den Master-Key (falls noch nicht gemacht)
"""

import sqlite3

db_path = "emails.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("1️⃣  Lösche altes kaputtes IMAP-Passwort...")
cur.execute('UPDATE mail_accounts SET encrypted_imap_password = NULL WHERE name = "martina"')
conn.commit()
print("✅ Done")

print("\n2️⃣  Überprüfe Master-Key...")
cur.execute('SELECT encrypted_master_key FROM users WHERE username = "thomas"')
row = cur.fetchone()
if row and row[0]:
    print(f"✅ Master-Key vorhanden: {row[0][:50]}...")
else:
    print("⚠️  Kein Master-Key gefunden - führe fix_master_key.py aus!")

conn.close()

print("\n" + "="*60)
print("🎯 Nächste Schritte:")
print("="*60)
print("1. Gehe in die Web-UI")
print("2. Bearbeite den Mail-Account 'martina'")
print("3. Gib das GMX-Passwort ERNEUT ein")
print("4. Speichern")
print("5. Teste den Mail-Fetch")
