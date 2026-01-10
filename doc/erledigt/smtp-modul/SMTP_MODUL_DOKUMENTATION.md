# 📧 SMTP Sender Modul - Vollständige Dokumentation

**Phase H - SMTP Mail-Versand**  
**Erstellt:** Januar 2026  
**Status:** ✅ FERTIG - Produktiv seit Januar 2026

---

## 🎯 Übersicht

Das SMTP-Modul ermöglicht:

| Feature | Beschreibung |
|---------|--------------|
| **Email-Versand** | Antworten und neue Emails via SMTP |
| **Threading** | Korrekte In-Reply-To/References Header |
| **IMAP-Sync** | Automatisches Speichern im Sent-Ordner |
| **DB-Sync** | Lokale Speicherung für konsistente Ansicht |
| **Zero-Knowledge** | Alle Credentials verschlüsselt |

---

## 📁 Dateien

### Neue Dateien

| Datei | Beschreibung | Zeilen |
|-------|--------------|--------|
| `src/19_smtp_sender.py` | SMTP Sender Service | ~650 |
| `src/smtp_routes_for_web_app.py` | Flask Routes (zu integrieren) | ~300 |
| `static/js/smtp_sender.js` | Frontend Integration | ~350 |

### Zu ändernde Dateien

| Datei | Änderung |
|-------|----------|
| `src/01_web_app.py` | Routes aus `smtp_routes_for_web_app.py` einfügen |
| `src/02_models.py` | Optional: `is_sent`, `encrypted_to` Felder hinzufügen |
| `templates/email_detail.html` | Script-Include + data-account-id Attribut |

---

## 🔧 Installation

### Schritt 1: SMTP Service kopieren

```bash
cp src/19_smtp_sender.py /pfad/zu/KI-Mail-Helper/src/
```

### Schritt 2: Routes in web_app.py integrieren

Öffne `src/01_web_app.py` und füge am Anfang hinzu:

```python
from src.19_smtp_sender import (
    SMTPSender,
    OutgoingEmail,
    EmailRecipient,
    EmailAttachment,
    SendResult,
    send_reply_to_email,
    send_new_email
)
```

Dann kopiere die Route-Funktionen aus `smtp_routes_for_web_app.py` in die Datei.

### Schritt 3: Frontend einbinden

In `templates/email_detail.html`:

```html
<!-- Account-ID für SMTP verfügbar machen -->
<div data-account-id="{{ email.mail_account_id }}" style="display:none;"></div>

<!-- Script einbinden (vor </body>) -->
<script src="{{ url_for('static', filename='js/smtp_sender.js') }}"></script>
```

### Schritt 4: Optional - DB-Migration

Falls du gesendete Emails speziell markieren willst:

```python
# In src/02_models.py - RawEmail erweitern:

class RawEmail(Base):
    # ... bestehende Felder ...
    
    # NEU: Für gesendete Emails
    is_sent = Column(Boolean, default=False)  # True = von uns gesendet
    encrypted_to = Column(Text, nullable=True)  # Empfänger (verschlüsselt)
```

Migration erstellen:
```bash
alembic revision -m "add_sent_email_fields"
```

---

## 📡 API Endpoints

### 1. SMTP Status prüfen

```http
GET /api/account/<account_id>/smtp-status
```

**Response:**
```json
{
    "success": true,
    "configured": true,
    "server": "smtp.gmx.net",
    "port": 587,
    "encryption": "STARTTLS"
}
```

### 2. SMTP Verbindung testen

```http
POST /api/account/<account_id>/test-smtp
```

**Response:**
```json
{
    "success": true,
    "message": "SMTP-Verbindung zu smtp.gmx.net erfolgreich"
}
```

### 3. Antwort senden

```http
POST /api/email/<email_id>/send-reply
Content-Type: application/json

{
    "reply_text": "Vielen Dank für Ihre Nachricht...",
    "reply_html": "<p>Vielen Dank...</p>",
    "include_quote": true,
    "cc": ["cc@example.com"],
    "attachments": [
        {
            "filename": "dokument.pdf",
            "content_base64": "JVBERi0xLjQK...",
            "mime_type": "application/pdf"
        }
    ]
}
```

**Response:**
```json
{
    "success": true,
    "message_id": "<abc123.1704067200@example.com>",
    "saved_to_sent": true,
    "sent_folder": "Gesendet",
    "imap_uid": 456,
    "saved_to_db": true,
    "db_email_id": 789
}
```

### 4. Neue Email senden

```http
POST /api/account/<account_id>/send
Content-Type: application/json

{
    "to": ["empfaenger@example.com", "Name <email@domain.de>"],
    "cc": ["cc@example.com"],
    "bcc": ["bcc@example.com"],
    "subject": "Betreff der Email",
    "body_text": "Hallo,\n\nHier ist meine Nachricht...",
    "body_html": "<p>Hallo,</p><p>Hier ist meine Nachricht...</p>"
}
```

### 5. KI-Entwurf generieren + optional senden

```http
POST /api/email/<email_id>/generate-and-send
Content-Type: application/json

{
    "tone": "formal",
    "custom_instructions": "Termine für nächste Woche vorschlagen",
    "include_quote": true,
    "send_immediately": false
}
```

**Response:**
```json
{
    "success": true,
    "draft_text": "Sehr geehrter Herr Müller,\n\nvielen Dank...",
    "subject": "Re: Ihre Anfrage",
    "recipient": "mueller@example.com",
    "tone": "formal",
    "generation_time_ms": 1234,
    "sent": false
}
```

---

## 🔄 Threading-Mechanismus

### RFC 2822/5322 Header

Für korrektes Threading werden diese Header gesetzt:

| Header | Beschreibung | Beispiel |
|--------|--------------|----------|
| `Message-ID` | Eindeutige ID der Email | `<abc123.1704067200@example.com>` |
| `In-Reply-To` | Message-ID der Original-Email | `<original123@sender.com>` |
| `References` | Komplette Thread-Kette | `<first@a.com> <second@b.com>` |

### Beispiel: Thread-Aufbau

```
Email 1 (Original):
  Message-ID: <A@sender.com>
  
Email 2 (Antwort auf 1):
  Message-ID: <B@reply.com>
  In-Reply-To: <A@sender.com>
  References: <A@sender.com>
  
Email 3 (Antwort auf 2):
  Message-ID: <C@reply2.com>
  In-Reply-To: <B@reply.com>
  References: <A@sender.com> <B@reply.com>
```

---

## 📂 Sent-Ordner Synchronisation

Das Modul findet automatisch den Sent-Ordner via:

1. **Special-Use Flag** `\Sent` (RFC 6154)
2. **Bekannte Namen:** Sent, Gesendet, INBOX.Sent, [Gmail]/Sent Mail, etc.
3. **Case-Insensitive Suche**

Die Email wird via **IMAP APPEND** mit `\Seen` Flag gespeichert.

---

## 🔐 Security

### Zero-Knowledge Architektur

- SMTP-Credentials werden verschlüsselt in DB gespeichert
- Master-Key zum Entschlüsseln nur in Session
- Email-Inhalte werden vor DB-Speicherung verschlüsselt
- Kein Logging von Passwörtern oder Inhalten

### Credential-Fallback

Falls SMTP-Username/Passwort nicht separat konfiguriert:
→ Automatischer Fallback auf IMAP-Credentials (funktioniert bei den meisten Providern)

---

## 🧪 Testing

### Python Shell Test

```python
from src.02_models import MailAccount, db
from src.19_smtp_sender import SMTPSender

# Account laden
account = MailAccount.query.first()
master_key = "dein-master-key"

# Sender erstellen
sender = SMTPSender(account, master_key)

# Konfiguration validieren
is_valid, error = sender.validate_configuration()
print(f"Konfiguration OK: {is_valid}, Fehler: {error}")

# Verbindung testen
success, message = sender.test_connection()
print(f"Verbindungstest: {success}, {message}")
```

### curl Test

```bash
# SMTP Status
curl -X GET http://localhost:5001/api/account/1/smtp-status \
  -H "Cookie: session=..."

# Antwort senden
curl -X POST http://localhost:5001/api/email/123/send-reply \
  -H "Content-Type: application/json" \
  -H "Cookie: session=..." \
  -d '{"reply_text": "Test-Antwort"}'
```

---

## 📊 Integration mit Phase G

### Workflow: Reply Draft → Edit → Send

```
┌─────────────────────────────────────────────────────────────┐
│  1. User klickt "Entwurf generieren"                        │
│     └─▶ POST /api/email/<id>/generate-reply                 │
│         └─▶ KI generiert Antwort-Text                       │
├─────────────────────────────────────────────────────────────┤
│  2. User sieht Entwurf, kann bearbeiten                     │
│     └─▶ Textarea zum Editieren                              │
├─────────────────────────────────────────────────────────────┤
│  3. User klickt "Absenden"                                  │
│     └─▶ POST /api/email/<id>/send-reply                     │
│         ├─▶ SMTP: Email senden                              │
│         ├─▶ IMAP: In Sent-Ordner speichern                  │
│         └─▶ DB: Lokal speichern                             │
├─────────────────────────────────────────────────────────────┤
│  4. Erfolgs-Meldung mit Details                             │
│     └─▶ Message-ID, Sent-Folder, etc.                       │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ Checkliste für Implementation

- [ ] `src/19_smtp_sender.py` kopieren
- [ ] Routes in `src/01_web_app.py` integrieren
- [ ] `static/js/smtp_sender.js` kopieren
- [ ] Template `email_detail.html` anpassen
- [ ] Optional: DB-Migration für `is_sent` Feld
- [ ] SMTP-Verbindung mit Test-Account prüfen
- [ ] Antwort senden und Threading verifizieren
- [ ] Sent-Ordner Synchronisation prüfen

---

## 🚀 Nächste Schritte

1. **Heute:** Dateien kopieren und integrieren
2. **Test:** SMTP-Verbindung mit deinem GMX-Account testen
3. **Phase G.1:** Reply Draft Generator + SMTP kombinieren
4. **Phase G.2:** Auto-Action Rules mit Newsletter-Archivierung

---

## 📚 Referenzen

- [RFC 2822: Internet Message Format](https://tools.ietf.org/html/rfc2822)
- [RFC 5322: Internet Message Format (updated)](https://tools.ietf.org/html/rfc5322)
- [RFC 6154: IMAP LIST Extension for Special-Use Mailboxes](https://tools.ietf.org/html/rfc6154)
- [Python smtplib Documentation](https://docs.python.org/3/library/smtplib.html)
- [IMAPClient Documentation](https://imapclient.readthedocs.io/)
