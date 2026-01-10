# Testing Guide - Kompletter Workflow

**Letzte Aktualisierung:** 27. Dezember 2025  
**Status:** DEK/KEK Pattern Complete (Phase 8b)

---

## 🔐 Zero-Knowledge Testing (DEK/KEK Pattern)

**Wichtig:** Das System verwendet Zero-Knowledge Encryption mit DEK/KEK Pattern. Alle sensiblen Daten sind verschlüsselt, der DEK existiert nur im RAM.

### DEK/KEK Architektur:
- **DEK (Data Encryption Key):** Zufällige 32 Bytes, verschlüsselt alle E-Mails
- **KEK (Key Encryption Key):** Aus Passwort abgeleitet (PBKDF2-600k), verschlüsselt DEK
- **Vorteil:** Passwort ändern = nur DEK re-encrypten (nicht alle E-Mails!)

### Was zu testen ist:
- ✅ DEK wird bei Registrierung generiert (zufällig)
- ✅ KEK wird bei Login abgeleitet (aus Passwort)
- ✅ DEK wird in Session geladen (nur RAM, nicht DB)
- ✅ DEK wird bei Logout gelöscht (session.clear())
- ✅ Session-Expire Detection (@app.before_request)
- ✅ Alle E-Mail-Inhalte verschlüsselt gespeichert
- ✅ Alle Credentials verschlüsselt gespeichert
- ✅ Server kann niemals auf Klartext zugreifen
- ✅ IMAP-Metadaten (UID, Folder, Flags) gespeichert
- ✅ Beide Mail-Fetcher (IMAP + Gmail OAuth)
- ✅ 2FA ohne Passwort in Session (nur pending_dek)

**📖 Details:** [ZERO_KNOWLEDGE_COMPLETE.md](ZERO_KNOWLEDGE_COMPLETE.md)

---

## 🧪 DEK/KEK Migration Testing (Phase 8b)

### Test 1: Neuer User (Clean DEK/KEK)
```bash
# Neue DB anlegen
mv emails.db emails.db.backup
python -m src.00_main --init

# Web-App starten
python -m src.01_web_app

# Registrieren → Mail-Account → Mails abrufen
# Prüfe DB:
sqlite3 emails.db "SELECT id, LENGTH(salt), LENGTH(encrypted_dek), encrypted_master_key FROM users;"
# Output: 1|44|<number>|NULL  ✅ (kein encrypted_master_key!)
```

### Test 2: Alter User Migration (encrypted_master_key → encrypted_dek)
```bash
# Restore alte DB
mv emails.db.backup emails.db

# Migration ausführen
python scripts/migrate_to_dek_kek.py
# → Passwort eingeben

# Prüfe DB:
sqlite3 emails.db "SELECT id, LENGTH(encrypted_dek), LENGTH(encrypted_master_key) FROM users;"
# Output: 1|<number>|<number>  ✅ (beide vorhanden)

# Login testen → Mails sollten lesbar sein
```

### Test 3: Session Security
```bash
# Login → Dashboard
# Session-File prüfen:
ls -lah .flask_sessions/
# DEK ist dort (verschlüsselt mit Flask SECRET_KEY)

# Logout → Session sollte gelöscht sein
# .flask_sessions/ File weg oder leer
```

---

## 🚀 Quick Start (20 Min)

### Phase 0: Setup
```bash
# Terminal 1: Ollama starten
sudo systemctl start ollama
ollama pull llama3.2  # Erste Ausführung: ~10 Min
systemctl status ollama
```

### Phase 1: Web-App starten
```bash
# Terminal 2:
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate
python3 -m src.00_main --serve
# http://localhost:5000
```

### Phase 2: User registrieren
1. **Registrieren** → http://localhost:5000/register
   - Benutzername: `thomas`
   - Email: `thomas@example.com`
   - Passwort: `TestPassword123!`
   
   ✅ DEK + KEK werden automatisch erstellt!

### Phase 3: Login
- Benutzername: `thomas`
- Passwort: `TestPassword123!`

✅ Master-Key wird mit Passwort entschlüsselt in Session geladen!

### Phase 4: Mail-Account hinzufügen
**Einstellungen** → **Neuen Account hinzufügen**

| Feld | Wert |
|------|------|
| Account-Name | Martina GMX |
| IMAP-Server | imap.gmx.net |
| IMAP-Port | 993 |
| Verschlüsselung | SSL/TLS |
| Benutzername | test-account@example.com |
| IMAP-Passwort | `[dein-gmx-passwort]` |

✅ Passwort wird mit Master-Key verschlüsselt!  
✅ Cron Master-Key wird aktualisiert!

### Phase 5: Mails abholen (Web-UI)
**Dashboard** → Mail-Account "Martina" → **Fetch Mails**

```
✅ Verbunden mit imap.gmx.net
📧 19 Mails gefunden
✅ 0 Mails gespeichert (Duplikate übersprungen)
```

### Phase 6: Mails verarbeiten (AI)
```bash
# Terminal 3:
cd /home/thomas/projects/KI-Mail-Helper
python3 -m src.00_main --process-once
```

**Erwartete Ausgabe:**
```
🚀 Starte Mail-Verarbeitung...
👤 Verarbeite User: thomas
🧾 Verarbeite 19 gespeicherte Mails...
🤖 Analysiere gespeicherte Mail: [Subject 1]...
✅ Mail verarbeitet: Score=8, Farbe=rot
✅ Mail verarbeitet: Score=5, Farbe=gelb
...
🎉 Fertig! 19 Mails verarbeitet
```

### Phase 7: Dashboard ansehen
Refresh: **http://localhost:5000/dashboard**

✅ 3×3-Matrix mit Mails  
✅ Rote/Gelbe/Grüne Farben  
✅ Listenansicht mit Scores

### Phase 8: Tag-System testen (Phase 10)

#### Auto-Tagging
```bash
# Re-process Emails mit Tag-Code
python3 scripts/reset_base_pass.py
# → Dashboard → "Jetzt verarbeiten"
```

**Erwartetes Verhalten:**
- ✅ KI schlägt 1-5 Tags vor (suggested_tags)
- ✅ Tags werden automatisch erstellt (EmailTag)
- ✅ Tags werden automatisch zugewiesen (EmailTagAssignment)
- ✅ Tags erscheinen in Liste + Detail

#### Tag-Management UI
```
Navigiere zu: http://localhost:5000/tags
```

**Teste:**
1. ✅ **Create Tag**: Name + Farbe wählen → Tag erstellt
2. ✅ **Edit Tag**: Name/Farbe ändern → gespeichert
3. ✅ **Delete Tag**: Tag löschen → EmailTagAssignments CASCADE gelöscht
4. ✅ **Email Count**: Anzahl E-Mails pro Tag korrekt

#### Tag-Assignment (Email Detail)
```
# Mail öffnen → Tag-Bereich
```

**Teste:**
1. ✅ **Add Tag**: "Tag hinzufügen" → Dropdown → Zuweisen
2. ✅ **Remove Tag**: X-Button auf Badge → Bestätigen → entfernt
3. ✅ **Duplicate Prevention**: Gleichen Tag 2x zuweisen → Fehler
4. ✅ **Learning Integration**: Manuelles Add/Remove → `user_override_tags` gesetzt

#### Tag-Filter (Dashboard)
```
# Dashboard → Filter-Bereich
```

**Teste:**
1. ✅ **Single Tag**: 1 Tag wählen → nur Mails mit diesem Tag
2. ✅ **Multi-Tag**: Strg/Cmd + Mehrere Tags → Mails mit diesen Tags
3. ✅ **Kombination**: Tag + Farbe + Done + Suche → korrekte Filterung
4. ✅ **Performance**: 100 Emails = 2 Queries (nicht 101)

#### Learning System
```bash
# DB prüfen nach manueller Tag-Änderung
sqlite3 emails.db "SELECT id, user_override_tags, correction_timestamp FROM processed_emails WHERE user_override_tags IS NOT NULL;"
```

**Erwartetes Output:**
```
12|Rechnung,Finanzen,Wichtig|2025-12-28 15:30:45
```

✅ `user_override_tags`: Komma-separierte Tag-Namen  
✅ `correction_timestamp`: Zeitstempel der Änderung

---

## 🔄 Automation testen

### Cron-Job aktivieren
```bash
sudo systemctl enable mail-helper-processor.timer
sudo systemctl start mail-helper-processor.timer
sudo systemctl status mail-helper-processor.timer
```

### Logs folgen
```bash
sudo journalctl -u mail-helper-processor -f
```

**Alle 15 Min sollte das passieren:**
```
Listening on 127.0.0.1:11434
🧾 Verarbeite X gespeicherte Mails...
✅ Mail verarbeitet...
```

---

## 🔐 Encryption Verification

```bash
python3 << 'EOF'
import sqlite3
conn = sqlite3.connect('emails.db')
cursor = conn.cursor()

# User + Master-Keys
cursor.execute("SELECT id, username, salt, encrypted_master_key FROM users")
for row in cursor.fetchall():
    print(f"User {row[0]} ({row[1]})")
    print(f"  Salt: {row[2][:20]}...")
    print(f"  Encrypted MK: {row[3][:20]}...")

# Mail Accounts + Passwords
cursor.execute("""
    SELECT m.id, m.name, m.encrypted_imap_password, u.username
    FROM mail_accounts m
    JOIN users u ON m.user_id = u.id
""")
for row in cursor.fetchall():
    print(f"Account {row[0]} ({row[1]}, User: {row[3]})")
    print(f"  Encrypted PWD: {row[2][:20] if row[2] else 'NULL'}...")

# RawEmails
cursor.execute("SELECT COUNT(*) FROM raw_emails")
print(f"\nRawEmails: {cursor.fetchone()[0]}")

# ProcessedEmails
cursor.execute("SELECT COUNT(*) FROM processed_emails")
print(f"ProcessedEmails: {cursor.fetchone()[0]}")

conn.close()
EOF
```

---

## 🐛 Troubleshooting

### Problem: `IMAP Fehler: authentication failed` beim `--process-once`

**Ursache:** Cron Master-Key ist kaputt oder veraltet

**Lösung:**
1. Gehe in Web-UI: **Settings** → **Mail Accounts** → Edit
2. **Neues Passwort speichern** (oder gleiches Passwort)
3. Das aktualisiert den Cron Master-Key!
4. Versuche erneut: `python3 -m src.00_main --process-once`

---

### Problem: `Keine Emails in Liste, obwohl fetch arbeitet`

**Ursache:** RawEmails existieren, aber nicht verarbeitet

**Prüfe:**
```bash
python3 << 'EOF'
import sqlite3
conn = sqlite3.connect('emails.db')
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM raw_emails")
raw = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM processed_emails")
proc = cursor.fetchone()[0]
print(f"RawEmails: {raw}, ProcessedEmails: {proc}")
conn.close()
EOF
```

**Falls RawEmails > 0 und ProcessedEmails = 0:**
```bash
# Manuell verarbeiten:
python3 -m src.00_main --process-once

# Oder auf Cron Timer warten (15 Min)
sudo systemctl status mail-helper-processor.timer
```

---

### Problem: `Ollama: command not found`

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl start ollama
ollama pull llama3.2
```

---

### Problem: `Master-Key Entschlüsselung fehlgeschlagen`

**Ursache:** Falsches Passwort beim Login

**Lösung:** Passwort neu eingeben, Browser-Cache löschen

---

### Problem: `Connection refused` auf Port 11434

**Ursache:** Ollama läuft nicht

```bash
# Überprüfen
systemctl status ollama

# Starten
sudo systemctl start ollama

# Oder manuell
ollama serve  # In anderem Terminal
```

---

## 🧪 Unit Tests

```bash
# Alle Tests
python3 -m pytest tests/ -v

# Einzeln
python3 -m pytest tests/test_sanitizer.py -v
python3 -m pytest tests/test_scoring.py -v
python3 -m pytest tests/test_ai_client.py -v
```

---

## 📊 Befehls-Cheatsheet

| Befehl | Funktion |
|--------|----------|
| `python3 -m src.00_main --serve` | Web-Dashboard starten |
| `python3 -m src.00_main --process-once` | Mails mit AI verarbeiten |
| `python3 -m src.00_main --fetch-only` | Nur Mails abholen |
| `python3 -m src.00_main --init-db` | Datenbank neu initialisieren |
| `systemctl status ollama` | Ollama Status |
| `ollama pull llama3.2` | Neues Modell laden |
| `systemctl status mail-helper-processor.timer` | Cron-Job Status |
| `sudo journalctl -u mail-helper-processor -f` | Live-Logs |

---

## 🔑 Master-Key System

```
Registration:
  Passwort → PBKDF2(Passwort, Salt) → Master-Key
  Master-Key + Passwort → AES-256-GCM → encrypted_master_key (DB)
  Master-Key + SERVER_MASTER_SECRET → AES-256-GCM → encrypted_master_key_for_cron (DB)

Login:
  Passwort + encrypted_master_key (DB) → AES-256-GCM → Master-Key (Session)
  Master-Key → SERVER_MASTER_SECRET → AES-256-GCM → encrypted_master_key_for_cron (aktualisiert)

Add Mail Account:
  IMAP-Passwort + Master-Key (Session) → AES-256-GCM → encrypted_imap_password (DB)

Cron Job (--process-once):
  encrypted_master_key_for_cron (DB) + SERVER_MASTER_SECRET → AES-256-GCM → Master-Key
  Master-Key + encrypted_imap_password → AES-256-GCM → IMAP-Passwort (Memory)
  IMAP-Passwort → IMAP-Verbindung → fetch_new_emails()
```

---

## ✅ Vollständiger Test-Checklist

- [ ] Ollama läuft (`systemctl status ollama`)
- [ ] Model geladen (`ollama pull llama3.2`)
- [ ] Web-App startet (`python3 -m src.00_main --serve`)
- [ ] User registrieren kann (`/register`)
- [ ] Login funktioniert
- [ ] Mail-Account hinzufügen kann
- [ ] `--fetch-only` funktioniert (19 Mails)
- [ ] `--process-once` funktioniert (19 verarbeitet)
- [ ] Dashboard zeigt Mails und Matrix
- [ ] Cron-Job läuft (`systemctl status mail-helper-processor.timer`)
- [ ] Logs sind sauber (`sudo journalctl -u mail-helper-processor`)

---

**Status:** Alle Tests bestanden = **Production Ready** ✅
