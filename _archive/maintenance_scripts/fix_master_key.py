#!/usr/bin/env python3
"""
🔧 Master-Key Reparatur-Script (VERALTET - nur für Migrations-Zwecke)

ACHTUNG: Dieses Script war für eine einmalige Migrations-Reparatur gedacht.
Wenn du das liest, ist es wahrscheinlich nicht mehr nötig!

Erwäge: Lösche dieses Script oder verschiebe es nach _archive/
"""

import sys
import sqlite3
import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import importlib

encryption = importlib.import_module('src.08_encryption')

print("⚠️  WARNUNG: Dieses Script ist veraltet und war für Migrations-Zwecke gedacht.")
print("    Wenn du unsicher bist, brich ab mit Ctrl+C.\n")

db_path = "emails.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Interaktive User-Auswahl
cur.execute('SELECT id, username FROM users')
users = cur.fetchall()

if not users:
    print("❌ Keine User gefunden!")
    sys.exit(1)

print("👥 Verfügbare User:")
for u in users:
    print(f"   {u['id']}: {u['username']}")
print()

try:
    user_id = int(input("User-ID eingeben: "))
except (ValueError, KeyboardInterrupt):
    print("\n❌ Abgebrochen")
    sys.exit(1)

cur.execute('SELECT id, username, salt FROM users WHERE id = ?', (user_id,))
user = cur.fetchone()

if not user:
    print("❌ User nicht gefunden")
    sys.exit(1)

print(f"✅ User gefunden: {user['username']}")
print(f"   Salt in DB: {user['salt'][:40]}...")
print()

# ✅ Sichere Passwort-Eingabe mit getpass (nicht sichtbar, kein Logging)
print("🔐 Master-Passwort wird benötigt für:")
print(f"   User: {user['username']}")
print()
user_password = getpass.getpass("🔒 Master-Passwort eingeben: ")

if not user_password:
    print("❌ Passwort darf nicht leer sein!")
    sys.exit(1)

print("\n🔐 Schritt 1: Master-Key mit Salt generieren")
master_key = encryption.EncryptionManager.generate_master_key(user_password, user['salt'])
print(f"✅ Master-Key: {master_key[:40]}...")
print()

print("🔒 Schritt 2: Master-Key mit deinem Passwort verschlüsseln")
encrypted_master_key = encryption.EncryptionManager.encrypt_master_key(master_key, user_password)
print(f"✅ Encrypted Master-Key: {encrypted_master_key[:40]}...")
print()

print("💾 Schritt 3: Encrypted Master-Key in DB schreiben")
cur.execute(
    'UPDATE users SET encrypted_master_key = ? WHERE id = ?',
    (encrypted_master_key, user['id'])
)
conn.commit()
print("✅ Master-Key in DB aktualisiert!")
print()

print("✅ Schritt 4: Verifikation - entschlüsseln testen")
try:
    decrypted = encryption.EncryptionManager.decrypt_master_key(encrypted_master_key, user_password)
    if decrypted == master_key:
        print("✅ ERFOLG! Master-Key korrekt verschlüsselt und dekodiert!")
        print(f"   Original:     {master_key[:40]}...")
        print(f"   Dekodiert:    {decrypted[:40]}...")
    else:
        print("❌ Mismatch!")
        sys.exit(1)
except Exception as e:
    print(f"❌ Fehler: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("🎉 FERTIG!")
print()
print("Der Master-Key wurde erfolgreich repariert und in die Datenbank geschrieben.")
print("Alle Mail-Passwörter dieses Users werden jetzt korrekt verschlüsselt.")

conn.close()
