# Mail Helper - Multi-Auth Setup Guide

Diese Dokumentation erklärt, wie du **Google OAuth** und **IMAP** in Mail Helper konfigurierst.

## 🚀 Überblick

Mail Helper unterstützt **zwei Authentifizierungsmethoden** für E-Mail-Konten:

1. **OAuth 2.0** - Sicher, ohne Passwort-Speicherung (empfohlen für Gmail/Outlook)
   - ✅ Automatische Token-Erneuerung
   - ✅ Kein App-Passwort nötig
   - ✅ Höhere Sicherheit
   
2. **IMAP/SMTP** - Traditionelle Authentifizierung (für alle Provider)
   - ✅ Universell unterstützt
   - ✅ Bidirektional (Empfangen + Versenden)
   - ✅ Ordner-Verwaltung

**Alle Methoden** speichern Credentials **verschlüsselt** mit AES-256-GCM.

---

## 📋 Voraussetzungen

1. Mail Helper läuft auf `http://localhost:5000`
2. Du hast einen User-Account registriert & bist eingeloggt
3. Dein Master-Key ist eingerichtet (automatisch bei Registration)

---

## 🔐 Google OAuth Setup

### Schritt 1: Google Cloud Console vorbereiten

1. Gehe zu [Google Cloud Console](https://console.cloud.google.com)
2. Erstelle ein **neues Projekt**: "Mail Helper"
3. Suche nach der **Gmail API** und aktiviere sie
4. Gehe zu **Anmeldedaten** → **OAuth-Zustimmungsbildschirm**
   - Externe Zustimmung wählen
   - App-Name: "Mail Helper"
   - User-Support-Email: Deine E-Mail-Adresse
5. Gehe zu **Anmeldedaten** → **Neue Anmeldedaten** → **OAuth-2.0-Client-ID**
   - Anwendungstyp: **Webapplikation**
   - Name: "Mail Helper Web"
   - Autorisierte Redirect-URIs hinzufügen:
     ```
     http://localhost:5000/settings/mail-account/google/callback
     ```
   - **Erstellen**

### Schritt 2: Credentials kopieren

Nach der Erstellung siehst du einen Dialog mit:
- **Client-ID** (z.B. `xyz.apps.googleusercontent.com`)
- **Client-Secret** (z.B. `GOCSPX-...`)

Diese speicherst du sicher ab.

### Schritt 3: In Mail Helper hinzufügen

1. Öffne Mail Helper Web-App → **Einstellungen** (⚙️)
2. Klick **"Neuen Account hinzufügen"**
3. Wähle **Google OAuth**
4. Gib deine **Client-ID** und **Client-Secret** ein
5. Klick **"Weiter zu Google Anmeldung"**
6. Du wirst zu Google weitergeleitet
7. Nach erfolgreicher Anmeldung:
   - Dein Gmail-Konto wird automatisch hinzugefügt
   - Token wird verschlüsselt mit deinem Master-Key gespeichert
   - Refresh-Token ermöglicht automatische Token-Erneuerung

### Schritt 4: Test

1. Gehe zu **Einstellungen** → Mail-Accounts-Tabelle
2. Klick **"Abrufen"** neben deinem Gmail-Account
3. Bei Erfolg siehst du eine ✅ Benachrichtigung mit der Anzahl neuer Mails

---

## 📧 IMAP/SMTP Setup

### Verfügbare Provider

#### Gmail mit App-Passwort

1. Aktiviere 2-Faktor-Authentifizierung auf [myaccount.google.com](https://myaccount.google.com/security)
2. Gehe zu **Sicherheit** → **App-Passwörter**
3. Wähle **Mail** und **Windows Computer**
4. Google generiert ein 16-stelliges Passwort → **Kopieren**

Dann in Mail Helper:
```
IMAP-Server:    imap.gmail.com
IMAP-Port:      993
IMAP-Verschl.:  SSL
Username:       deine@gmail.com
Passwort:       <16-stelliges App-Passwort>

SMTP-Server:    smtp.gmail.com
SMTP-Port:      587
SMTP-Verschl.:  STARTTLS
Username:       deine@gmail.com
Passwort:       <16-stelliges App-Passwort>
```

#### GMX

```
IMAP-Server:    imap.gmx.net
IMAP-Port:      993
IMAP-Verschl.:  SSL
Username:       deine@gmx.de
Passwort:       Dein GMX-Passwort

SMTP-Server:    smtp.gmx.net
SMTP-Port:      587
SMTP-Verschl.:  STARTTLS
Username:       deine@gmx.de
Passwort:       Dein GMX-Passwort
```

#### Outlook / Hotmail

```
IMAP-Server:    outlook.office365.com
IMAP-Port:      993
IMAP-Verschl.:  SSL
Username:       deine@outlook.com
Passwort:       Dein Outlook-Passwort

SMTP-Server:    smtp.office365.com
SMTP-Port:      587
SMTP-Verschl.:  STARTTLS
Username:       deine@outlook.com
Passwort:       Dein Outlook-Passwort
```

### Schritt 1: In Mail Helper hinzufügen

1. Öffne Mail Helper → **Einstellungen**
2. Klick **"Neuen Account hinzufügen"**
3. Wähle **Manuell (IMAP)**
4. Fülle alle Felder aus (IMAP + optional SMTP)
5. **Speichern**

### Schritt 2: Test

1. Gehe zu **Einstellungen** → Mail-Accounts-Tabelle
2. Klick **"Abrufen"** neben deinem Account
3. Bei Erfolg siehst du ✅ mit Anzahl neuer Mails

---

## 🔄 Automatische Mail-Abholung

### Cron Job Setup (Linux/WSL)

1. Öffne Cron-Editor:
   ```bash
   crontab -e
   ```

2. Füge diese Zeile hinzu (alle 15 Minuten):
   ```bash
   */15 * * * * cd /home/thomas/projects/KI-Mail-Helper && python3 -m src.00_main --cron
   ```

3. Speichern (`:wq` in Vim)

**Hinweis**: Für OAuth funktioniert der Cron-Job nur mit unverschlüsselter Master-Key Speicherung oder mit Service-Token-Authentifizierung.

---

## 🔒 Sicherheit

### Encryption

- **Master-Key**: Mit PBKDF2 aus deinem Passwort abgeleitet (Salt: 32 Bytes, Iterations: 100.000)
- **Passwords/Tokens**: Mit AES-256-GCM verschlüsselt (IV: 12 Bytes, Tag: 16 Bytes)
- **Speicherung**: Nur verschlüsselte Werte in der Datenbank

### Datenschutz

- Tokens/Passwörter werden niemals im Log gezeigt
- Session-basierte Speicherung (RAM) nur während Authentifizierung
- Refresh-Tokens für automatische Token-Erneuerung

---

## ❌ Fehlerbehandlung

### "Master-Key nicht im Session"
- Behebung: Logout und erneut einloggen
- Der Master-Key wird beim Login entschlüsselt

### "Token-Austausch fehlgeschlagen" (OAuth)
- Überprüfe dass Client-ID/Secret korrekt sind
- Verifiziere dass Redirect-URI in Google Cloud Console konfiguriert ist
- Stelle sicher dass du nicht zu lange wartest (Code verfällt nach ~10 Sekunden)

### "Verbindungsfehler" (IMAP)
- Überprüfe Server-Adresse und Port
- Testen Sie mit einem Mail-Client (Outlook, Thunderbird) zur Verifizierung
- Gmail benötigt App-Passwort, nicht das normale Passwort
- Manche Provider blockieren Zugriff → Schau in Account-Sicherheitseinstellungen

### "Keine neuen Mails"
- Das ist normal! Nur ungelesene Mails werden abgeholt
- Markiere eine Mail im Mail-Client als ungelesen und versuche erneut

---

## 📝 Testing

Starte das Test-Skript:

```bash
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate
python3 test_mail_fetcher.py
```

Dies testet:
- ✅ IMAP-Verbindung (wenn TEST_IMAP_* env-vars gesetzt)
- ✅ Google OAuth Manager
- ✅ Encryption/Decryption
- ✅ Database-Struktur

---

## 🔄 Auth-Type Migration

Wenn du bereits Accounts hast und auf die neue Multi-Auth Architektur migrierst:

```bash
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate

# Alembic Migration ausführen
alembic upgrade head
```

Die Migration setzt automatisch:
- Accounts mit `oauth_provider != NULL` → `auth_type = "oauth"`
- Alle anderen → `auth_type = "imap"`

---

## 🚀 Web-App starten

```bash
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate
python3 src/01_web_app.py
```

Öffne dann http://localhost:5000 im Browser.

---

## 📚 Weitere Ressourcen

- [Gmail API Docs](https://developers.google.com/gmail/api/guides)
- [IMAP Server-Dokumentationen](https://www.fastmail.com/help/other/imapconfigure.html)
- [RFC 3501 - IMAP Protocol](https://tools.ietf.org/html/rfc3501)
