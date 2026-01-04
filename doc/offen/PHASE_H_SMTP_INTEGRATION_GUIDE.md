# 📧 Phase H: SMTP Mail-Versand - Implementation Complete! ✅

**Status:** ✅ **BEREIT ZUM TESTEN**  
**Datum:** 04. Januar 2026  
**Integration:** Phase H - Ausgehender Mail-Versand

---

## 🎯 Was wurde implementiert?

### Backend Implementation ✅

#### 1. SMTP Sender Service ([src/19_smtp_sender.py](../src/19_smtp_sender.py))
- ✅ RFC 2822 konforme Message-ID Generierung
- ✅ Threading via In-Reply-To und References Header
- ✅ Automatisches Speichern im Sent-Ordner via IMAP APPEND
- ✅ Lokale DB-Synchronisation für konsistente Ansicht
- ✅ Zero-Knowledge: Alle Credentials verschlüsselt
- ✅ Angepasst an aktuelles System:
  - `EncryptionManager.encrypt_data()` / `decrypt_data()`
  - IMAPClient 3.0.1 API
  - SessionLocal() für DB-Zugriff

#### 2. API Endpoints ([src/01_web_app.py](../src/01_web_app.py))
- ✅ `GET /api/account/<id>/smtp-status` - SMTP-Status prüfen
- ✅ `POST /api/account/<id>/test-smtp` - SMTP-Verbindung testen
- ✅ `POST /api/emails/<id>/send-reply` - Antwort senden
- ✅ `POST /api/account/<id>/send` - Neue Email senden
- ✅ `POST /api/emails/<id>/generate-and-send` - KI-Draft + optional senden

### Frontend UI ✅

#### SMTP-Felder bereits vorhanden
- ✅ [templates/add_mail_account.html](../templates/add_mail_account.html) - SMTP-Server, Port, Encryption, Username, Password
- ✅ [templates/edit_mail_account.html](../templates/edit_mail_account.html) - SMTP-Felder editierbar
- ✅ Verschlüsselte Speicherung bereits implementiert

---

## 🚀 TESTEN IM UI - Schritt für Schritt

### Schritt 1: Server starten

```bash
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate
python3 -m src.00_main --serve --https
```

Server läuft auf: **https://localhost:5001**

---

### Schritt 2: SMTP-Credentials konfigurieren

1. **Dashboard öffnen** → https://localhost:5001/dashboard
2. **Mail-Account bearbeiten** → Klick auf "Bearbeiten" bei deinem Account
3. **SMTP-Felder ausfüllen:**

#### Beispiel: GMX
```
SMTP-Server:       smtp.gmx.net
SMTP-Port:         587
Verschlüsselung:   STARTTLS
SMTP-Benutzername: deine@email.gmx.net
SMTP-Passwort:     dein-passwort
```

#### Beispiel: Gmail
```
SMTP-Server:       smtp.gmail.com
SMTP-Port:         587
Verschlüsselung:   STARTTLS
SMTP-Benutzername: deine@email.gmail.com
SMTP-Passwort:     App-Passwort (nicht dein Gmail-Passwort!)
```

**Wichtig:** Falls SMTP-Benutzername/Passwort leer gelassen → verwendet IMAP-Credentials

4. **Speichern** → Credentials werden verschlüsselt in DB gespeichert

---

### Schritt 3: SMTP-Verbindung testen (API Call)

Du kannst die Verbindung via Browser-Console oder `curl` testen:

#### Option A: Browser Console (F12 → Console)

```javascript
// Account-ID ermitteln (steht im HTML)
const accountId = 1; // Deine Account-ID

// SMTP-Status prüfen
fetch(`/api/account/${accountId}/smtp-status`, {
    method: 'GET',
    credentials: 'include'
})
.then(r => r.json())
.then(data => console.log('Status:', data));

// SMTP-Verbindung testen
fetch(`/api/account/${accountId}/test-smtp`, {
    method: 'POST',
    credentials: 'include',
    headers: {'Content-Type': 'application/json'}
})
.then(r => r.json())
.then(data => console.log('Test:', data));
```

**Erwartetes Ergebnis:**
```json
{
  "success": true,
  "message": "SMTP-Verbindung zu smtp.gmx.net erfolgreich"
}
```

#### Option B: curl (im Terminal)

```bash
# SMTP-Status prüfen
curl -X GET "https://localhost:5001/api/account/1/smtp-status" \
  --cookie "session=DEINE_SESSION_COOKIE" \
  -k

# SMTP-Verbindung testen
curl -X POST "https://localhost:5001/api/account/1/test-smtp" \
  --cookie "session=DEINE_SESSION_COOKIE" \
  -k
```

---

### Schritt 4: Test-Antwort senden

1. **Email öffnen** → Dashboard → Email auswählen
2. **Email-ID ermitteln** → steht in der URL: `/email/123` → ID ist `123`
3. **Browser Console öffnen** (F12 → Console)
4. **Antwort senden:**

```javascript
const emailId = 123; // Deine Email-ID

fetch(`/api/emails/${emailId}/send-reply`, {
    method: 'POST',
    credentials: 'include',
    headers: {
        'Content-Type': 'application/json',
        // CSRF Token aus Cookie oder Meta-Tag
        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content
    },
    body: JSON.stringify({
        reply_text: "Vielen Dank für Ihre Nachricht!\n\nMit freundlichen Grüßen",
        include_quote: true  // Original-Text zitieren
    })
})
.then(r => r.json())
.then(data => console.log('Antwort gesendet:', data));
```

**Erwartetes Ergebnis:**
```json
{
  "success": true,
  "message_id": "<abc123.1704067200@gmx.net>",
  "saved_to_sent": true,
  "sent_folder": "Gesendet",
  "imap_uid": 456,
  "saved_to_db": true,
  "db_email_id": 789
}
```

---

### Schritt 5: Neue Email senden

```javascript
const accountId = 1; // Deine Account-ID

fetch(`/api/account/${accountId}/send`, {
    method: 'POST',
    credentials: 'include',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content
    },
    body: JSON.stringify({
        to: ["empfaenger@example.com"],
        subject: "Test-Email aus KI-Mail-Helper",
        body_text: "Hallo,\n\ndies ist eine Test-Email.\n\nGrüße"
    })
})
.then(r => r.json())
.then(data => console.log('Email gesendet:', data));
```

---

### Schritt 6: KI-Draft generieren + senden

```javascript
const emailId = 123; // Email auf die du antworten willst

fetch(`/api/emails/${emailId}/generate-and-send`, {
    method: 'POST',
    credentials: 'include',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content
    },
    body: JSON.stringify({
        tone: "formal",                    // formal, friendly, brief, decline
        custom_instructions: "Termine für nächste Woche vorschlagen",
        include_quote: true,
        send_immediately: true            // false = nur Draft generieren
    })
})
.then(r => r.json())
.then(data => console.log('KI-Draft+Send:', data));
```

**Erwartetes Ergebnis:**
```json
{
  "success": true,
  "draft_text": "Sehr geehrte/r ...",
  "subject": "Re: Original-Betreff",
  "recipient": "original@sender.com",
  "sent": true,
  "message_id": "<abc123...>",
  "saved_to_sent": true
}
```

---

## 🔍 Fehlersuche

### Problem: "Nicht authentifiziert"

**Ursache:** Session-Cookie fehlt oder abgelaufen

**Lösung:** 
1. Im Browser erneut einloggen
2. In Console testen (automatisches Cookie-Handling)

---

### Problem: "SMTP-Server nicht konfiguriert"

**Ursache:** SMTP-Felder nicht ausgefüllt

**Lösung:**
1. Dashboard → Account bearbeiten
2. SMTP-Server, Port, Username, Password eingeben
3. Speichern

---

### Problem: "Authentifizierung fehlgeschlagen"

**Ursache:** 
- Falsches Passwort
- 2FA/App-Passwort erforderlich (z.B. Gmail)

**Lösung Gmail:**
1. Google Account → Sicherheit → 2-Faktor-Authentifizierung
2. App-Passwörter → Neues App-Passwort erstellen
3. 16-stelliges Passwort kopieren → Als SMTP-Passwort verwenden

**Lösung GMX/Web.de:**
- Manchmal muss "Externe E-Mail-Programme" in den Einstellungen aktiviert werden

---

### Problem: "Sent-Ordner nicht gefunden"

**Ursache:** Server hat keinen Standard-Sent-Ordner

**Lösung:** Email wird trotzdem gesendet! Nur IMAP-Sync schlägt fehl.

---

## 📊 Logging & Debugging

### Server-Logs ansehen

```bash
# Terminal wo Server läuft
# Logs erscheinen automatisch
```

**Erfolgreicher Versand:**
```
INFO: ✉️ Email gesendet: Test-Email... an 1 Empfänger (Message-ID: <abc...>)
INFO: 📁 Email im Sent-Ordner gespeichert: Gesendet (UID: 456)
INFO: 💾 Email in DB gespeichert: ID 789
```

**Fehler:**
```
ERROR: SMTP-Fehler: Authentication failed
ERROR: Fehler beim IMAP APPEND: Sent folder not found
```

---

## 🎨 Nächster Schritt: Frontend-UI Integration (Optional)

Aktuell funktioniert der Versand via API. Für bessere UX kannst du:

### 1. "Antwort senden" Button in email_detail.html

Füge nach dem "Antwort-Entwurf generieren" Button ein:

```html
<button class="btn btn-primary w-100 mt-2" id="sendReplyBtn">
    📤 Antwort senden
</button>
```

### 2. Modal für Reply-Eingabe

```html
<!-- Reply-Modal -->
<div class="modal fade" id="sendReplyModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">📤 Antwort verfassen</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <textarea id="replyTextInput" class="form-control" rows="10" 
                          placeholder="Deine Antwort..."></textarea>
                <div class="form-check mt-2">
                    <input class="form-check-input" type="checkbox" id="includeQuoteCheck" checked>
                    <label class="form-check-label" for="includeQuoteCheck">
                        Original-Email zitieren
                    </label>
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Abbrechen</button>
                <button type="button" class="btn btn-primary" id="confirmSendBtn">
                    📤 Senden
                </button>
            </div>
        </div>
    </div>
</div>
```

### 3. JavaScript Event-Handler

```javascript
document.getElementById('sendReplyBtn').addEventListener('click', function() {
    // Modal öffnen
    const modal = new bootstrap.Modal(document.getElementById('sendReplyModal'));
    modal.show();
});

document.getElementById('confirmSendBtn').addEventListener('click', async function() {
    const emailId = {{ email.id }};
    const replyText = document.getElementById('replyTextInput').value;
    const includeQuote = document.getElementById('includeQuoteCheck').checked;
    
    try {
        const response = await fetch(`/api/emails/${emailId}/send-reply`, {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                reply_text: replyText,
                include_quote: includeQuote
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('✅ Email erfolgreich gesendet!');
            // Modal schließen
            bootstrap.Modal.getInstance(document.getElementById('sendReplyModal')).hide();
        } else {
            alert('❌ Fehler: ' + data.error);
        }
    } catch (error) {
        alert('❌ Netzwerk-Fehler: ' + error.message);
    }
});

// CSRF-Token Helper
function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
}
```

---

## ✅ Implementation Checklist

- [x] SMTP Sender Service adaptiert (`19_smtp_sender.py`)
- [x] API Endpoints hinzugefügt (`01_web_app.py`)
- [x] SMTP-Felder im UI vorhanden (`add/edit_mail_account.html`)
- [x] Encryption kompatibel (`EncryptionManager.encrypt_data()`)
- [x] IMAPClient 3.0.1 Unterstützung
- [x] Dependencies geprüft (alle vorhanden)
- [x] Testing Guide erstellt
- [ ] **Optional:** Frontend-UI für "Senden" Button
- [ ] **Optional:** Reply-Modal mit User-Input

---

## 🎯 Zusammenfassung

**Was funktioniert JETZT:**
- ✅ SMTP-Credentials verschlüsselt speichern
- ✅ SMTP-Verbindung testen (via API)
- ✅ Email-Antworten senden (via API)
- ✅ Neue Emails senden (via API)
- ✅ KI-Draft generieren + optional senden (via API)
- ✅ Automatisches Speichern im Sent-Ordner
- ✅ Lokale DB-Synchronisation
- ✅ RFC-konformes Threading

**Was du testen musst:**
1. SMTP-Credentials im UI eingeben
2. Verbindung via Browser-Console testen
3. Test-Antwort senden
4. In deinem Email-Client prüfen (Sent-Ordner + Empfänger-Postfach)

**Nächster Schritt:**
- Optional: UI-Buttons + Modal für bessere UX
- Oder: Direkt mit APIs arbeiten für spezielle Workflows

---

## 📝 Provider-spezifische Konfigurationen

### Gmail
```
SMTP-Server:       smtp.gmail.com
SMTP-Port:         587
Verschlüsselung:   STARTTLS
SMTP-Benutzername: deine@gmail.com
SMTP-Passwort:     16-stelliges App-Passwort (NICHT Gmail-Passwort!)
```

**App-Passwort erstellen:**
1. https://myaccount.google.com/security
2. 2-Faktor-Authentifizierung → App-Passwörter
3. "Mail" auswählen → Passwort generieren

### GMX / Web.de
```
SMTP-Server:       smtp.gmx.net (oder smtp.web.de)
SMTP-Port:         587
Verschlüsselung:   STARTTLS
SMTP-Benutzername: deine@gmx.net
SMTP-Passwort:     Dein GMX-Passwort
```

### Outlook.com / Hotmail
```
SMTP-Server:       smtp-mail.outlook.com
SMTP-Port:         587
Verschlüsselung:   STARTTLS
SMTP-Benutzername: deine@outlook.com
SMTP-Passwort:     Dein Outlook-Passwort
```

### Custom SMTP (z.B. Strato, 1&1, etc.)
```
SMTP-Server:       [von Provider gegeben]
SMTP-Port:         587 (STARTTLS) oder 465 (SSL)
Verschlüsselung:   STARTTLS oder SSL
SMTP-Benutzername: [von Provider gegeben]
SMTP-Passwort:     [von Provider gegeben]
```

---

**Status:** ✅ **READY TO TEST** 🚀
**Letzte Aktualisierung:** 04. Januar 2026
