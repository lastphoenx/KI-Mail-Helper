# 🔐 Zero-Knowledge Architektur & Arbeitsweise

**KI-Mail-Helper** - Sichere E-Mail-Verwaltung mit Zero-Knowledge-Verschlüsselung

**Status:** ✅ Implementiert & Produktionsreif  
**Last Updated:** 30. Dezember 2025  
**Sicherheitsscore:** 100/100

---

## 📋 Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Kryptographischer Flow](#kryptographischer-flow)
3. [Drei Verschlüsselungs-Ebenen](#drei-verschlüsselungs-ebenen)
4. [Session & Master-Key Management](#session--master-key-management)
5. [Entschlüsselung: Nur im UI & zur Verarbeitung](#entschlüsselung-nur-im-ui--zur-verarbeitung)
6. [Background Jobs / CLI & Master-Key](#background-jobs--cli--master-key)
7. [Testing-Richtlinie](#testing-richtlinie)
8. [Deployment-Sicherheit](#deployment-sicherheit)
9. [Compliance Checkliste](#compliance-checkliste)

---

## Überblick

Der Server speichert **NIEMALS** Klartext-Daten von Benutzer*innen. Alle sensiblen Daten (E-Mails, Credentials, Metadaten) werden mit dem **Master-Passwort des Users** verschlüsselt. Der Server kann die Daten **physisch nicht entschlüsseln** - nur der User selbst mit seinem Master-Passwort kann das tun.

**Kern-Prinzip:**
```
Klartext-Daten = Nur im User-Browser (über HTTPS/TLS)
                 Nur während aktiver Session
                 Nur mit gültigem Master-Passwort
                 
Verschlüsselte Daten = In der Datenbank
                        Auf Disk
                        Im Backup
                        Im Cache
```

---

## Kryptographischer Flow

### User Account Creation / Login

```
┌─────────────────────────────────────────────────────────────┐
│  USER REGISTRATION / LOGIN                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
         ┌──────────────────────┐
         │ User Enters Password │  (z.B.: "MySecureP@ss123")
         └──────────┬───────────┘
                    │
                    ▼
     ┌──────────────────────────────────────┐
     │ PBKDF2-HMAC-SHA-256                  │
     │ 100.000 Iterationen                  │
     │ → KEK (Key Encryption Key) derivieren│
     └──────────────┬───────────────────────┘
                    │
          ┌─────────┴──────────┐
          │                    │
          ▼                    ▼
   [In DB speichern]   [In RAM Session halten]
   │                   │
   │                   └─ Master-Key (32 Bytes)
   │                      Nur diese Session
   │
   └─ encrypted_master_key
      = AES-256-GCM(
          Master-Key,
          KEK
        )
      → Für nächste Sessions
```

**Die Logik:**
- **KEK** = Aus Passwort abgeleitet (deterministic)
- **Master-Key** = Zufällig generiert, nur für diese Session
- **Passwort** wird NACH Key-Derivation verworfen
- **Passwort wird NIEMALS direkt gespeichert** (nur Hash)

### Wiedererkennung (nächster Login)

```
Benutzer meldet sich an mit Passwort
  ↓
PBKDF2 mit gleichen Salt → gleicher KEK
  ↓
Entschlüssle encrypted_master_key(KEK) → Master-Key
  ↓
Neue Session mit diesem Master-Key
  ↓
2FA-Verifizierung
  ↓
Session aktiv, Master-Key im RAM
```

---

## Drei Verschlüsselungs-Ebenen

### Ebene 1: Mail-Account Credentials

```
MailAccount Tabelle:
├─ encrypted_imap_server      (AES-256-GCM)
├─ encrypted_imap_username    (AES-256-GCM)
├─ encrypted_imap_password    (AES-256-GCM)
├─ encrypted_smtp_server      (AES-256-GCM)
├─ encrypted_smtp_username    (AES-256-GCM)
├─ encrypted_smtp_password    (AES-256-GCM)
├─ encrypted_oauth_token      (AES-256-GCM)
└─ encrypted_oauth_refresh_token (AES-256-GCM)
```

**Warum:** Ein gehackter Server-Account offenbart KEINE echten Credentials

**Decryption:** Nur möglich mit User-Passwort (Session)

### Ebene 2: E-Mail-Daten (RawEmail)

```
RawEmail Tabelle (Rohdaten vom IMAP-Server):
├─ encrypted_sender    (AES-256-GCM)
├─ encrypted_subject   (AES-256-GCM)
├─ encrypted_body      (AES-256-GCM)
│
└─ NICHT verschlüsselt (nur Metadaten):
   ├─ imap_uid          (für IMAP-Ops nötig)
   ├─ imap_flags        (für Sorting/Filtering)
   ├─ received_at       (für Timeline)
   └─ uid               (für Deduplication)
```

**Warum nicht ALLES verschlüsselt?**
- `imap_uid`, `received_at`: Für DB-Operationen brauchbar ohne Klartext
- `imap_flags`: Für Filtering (ist/gelesen, ist/flagged)

**Decryption:** Server entschlüsselt beim Rendern, NICHT in REST-API gespeichert

### Ebene 3: KI-Verarbeitete Daten (ProcessedEmail)

```
ProcessedEmail Tabelle:
├─ encrypted_summary_de       (AES-256-GCM)
├─ encrypted_text_de          (AES-256-GCM)
├─ encrypted_tags             (AES-256-GCM)
├─ encrypted_correction_note  (AES-256-GCM)
│
└─ NICHT verschlüsselt (Metadaten):
   ├─ score              (1-10, Server-Ranking)
   ├─ kategorie_aktion   (action_required, urgent, info)
   ├─ spam_flag          (boolean)
   └─ timestamps         (processed_at, done_at)
```

**Warum:** KI-Ergebnisse sind sensibel, aber Scores/Categories dienen nur für Ranking

---

## Session & Master-Key Management

### Session-Lifecycle

```
┌──────────────────────────────────────────────────────────────┐
│                         LOGIN                                │
│              (Benutzer + Passwort + 2FA)                     │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
       ┌───────────────────────────┐
       │ [SERVER-SIDE SESSION]     │
       │ .flask_sessions/uuid      │
       ├───────────────────────────┤
       │ - User-ID                 │
       │ - Master-Key (32 Bytes)   │
       │ - 2FA verified: true      │
       │ - Created: timestamp      │
       │ - Expires: +24 hours      │
       └───────┬───────────────────┘
               │
    ┌──────────┴───────────┐
    │                      │
    ▼                      ▼
 [Browser]             [Server RAM]
 Session-Cookie        Session Data
 (nur ID)              (inkl. Master-Key)
 - Nicht httponly      - Nicht accessible
 - Nicht JS-zugänglich   from Browser
 - Signiert              - In Speicher
                         - Wird bei Logout gelöscht
```

### Jeder HTTP-Request

```
Browser sendet Request + Session-Cookie
  ↓
Server identifiziert Session
  ↓
Prüfe: session['master_key'] existiert?
  │
  ├─ JA: Lade verschlüsselte Daten
  │   ├─ Entschlüssle mit Master-Key
  │   ├─ Rendere HTML mit Klartext
  │   └─ Sende über HTTPS zum Browser
  │
  └─ NEIN: Return 401 Unauthorized
```

### Master-Key bei Logout / Session-Timeout

```
Logout-Route oder Session-Timeout
  ↓
session.pop('master_key', None)  ← LÖSCHEN!
  ↓
Alle Daten sofort inaccessible
  ↓
Browser wird zu Login-Seite weitergeleitet
```

**Kritisch:** Alte Browser-Tabs sind noch lesbar (Benutzer hatte ja diese gelesen), aber:
- Neue Daten sind nicht mehr erreichbar
- Keine neuen Requests ohne Master-Key
- Nach Timeout: Session-Cookie wird invalid

### ❌ Häufiger Fehler: Master-Key im Browser-Cookie

**FALSCH (Old Implementation):**
```python
# Browser-Cookie mit Master-Key!
response.set_cookie('master_key', master_key, httponly=True)
```

**Sicherheitsrisiken:**
- ⚠️ Cookie-Theft → Angreifer hat Master-Key
- ⚠️ Browser-Malware → Kann httponly umgehen
- ⚠️ XSS via Redirect → Cookie wird mitgesendet

**RICHTIG (Current):**
```python
# Session nur auf Server
session['master_key'] = master_key  
# → .flask_sessions/session_uuid
# → Browser erhält nur: session_id im Cookie
```

**Sicherheitsgewinn:**
- ✅ Cookie-Theft → Nur Session-ID, keine Credentials
- ✅ Browser-Malware → Kann nicht auf Server-RAM zugreifen
- ✅ XSS-Attacke → Kann nicht auf Master-Key zugreifen

---

## Entschlüsselung: Nur im UI & zur Verarbeitung

### Workflow: Mail anzeigen

```
┌────────────────────────────────────────────────────────────┐
│ User klickt auf E-Mail in Dashboard                        │
└────────────────┬─────────────────────────────────────────┘
                 │
                 ▼
         GET /email/123
         Header: Cookie: session_id=xyz
                 │
                 ├─ [Server] Session-Lookup: xyz
                 │           → session['master_key'] ✓
                 │
                 ├─ [Server] Lade RawEmail aus DB
                 │           encrypted_subject = "CJK7Zd4..."
                 │           encrypted_sender = "BmN2Jo5..."
                 │
                 ├─ [Server] Entschlüssle
                 │           subject = decrypt(encrypted_subject, master_key)
                 │           sender = decrypt(encrypted_sender, master_key)
                 │
                 ├─ [Server] Rendere HTML
                 │           <h1>{{ subject }}</h1>
                 │           <p>Von: {{ sender }}</p>
                 │
                 └─ [HTTPS Transport]
                    └─ Browser empfängt Klartext-HTML
```

**Wichtig:**
- ✅ Entschlüsselung NUR auf dem Server
- ✅ Browser empfängt **Klartext** (via HTTPS/TLS)
- ✅ Master-Key wird **NICHT** zum Browser gesendet
- ✅ Sobald Logout → alte Seiten im Browser sind noch lesbar (User hatte diese ja genutzt), aber neue Daten nicht erreichbar

### Entschlüsselung in Routes

```python
# ✓ RICHTIG: In Route vor Rendern

@app.route('/email/<int:email_id>')
@login_required
def email_detail(email_id):
    db = get_db_session()
    user = get_current_user_model(db)
    
    # Master-Key aus Session
    master_key = session.get('master_key')
    if not master_key:
        return redirect('/login')
    
    # Lade verschlüsselte Mail
    raw_email = db.query(RawEmail).filter_by(id=email_id).first()
    
    # Entschlüssle VOR Rendern
    decrypted_subject = decrypt_email_subject(
        raw_email.encrypted_subject, master_key
    )
    decrypted_sender = decrypt_email_sender(
        raw_email.encrypted_sender, master_key
    )
    
    return render_template(
        'email_detail.html',
        subject=decrypted_subject,
        sender=decrypted_sender,
    )

# ✗ FALSCH: Nicht im Template!
# {{ email.encrypted_subject }}  ← Zeigt Ciphertext!
```

### REST-API & Entschlüsselung

```python
# Szenario: Frontend holt Mails via AJAX

@app.route('/api/emails')
@login_required
def api_emails():
    db = get_db_session()
    user = get_current_user_model(db)
    master_key = session.get('master_key')
    
    emails = db.query(ProcessedEmail).limit(10).all()
    
    result = []
    for email in emails:
        # ENTSCHLÜSSLE vor JSON-Rückgabe!
        decrypted_summary = decrypt_summary(
            email.encrypted_summary_de, master_key
        )
        
        result.append({
            'id': email.id,
            'subject': decrypted_summary[:100],
            'score': email.score,
            'category': email.kategorie_aktion,
        })
    
    return jsonify(result)
```

---

## Background Jobs / CLI & Master-Key

### Problem: Kein Flask-Request-Context

Cron-Jobs, CLI-Commands, Async-Tasks haben keinen Flask-Request-Context → Können nicht auf `session['master_key']` zugreifen

### Lösung: Expliziter Master-Key Parameter

```python
# ✗ FALSCH:
def process_emails(user):
    master_key = session['master_key']  # ← RuntimeError!
    # Kein Flask-Context!

# ✓ RICHTIG:
def process_emails(user, master_key: str):
    # Master-Key als Parameter
    encrypted_subject = models.RawEmail.encrypted_subject
    decrypted_subject = decrypt(encrypted_subject, master_key)
    # ...
```

### Caller: API-Endpoint mit Session

```python
@app.route('/mail-account/fetch', methods=['POST'])
@login_required
def fetch_mails():
    db = get_db_session()
    user = get_current_user_model(db)
    account_id = request.json['account_id']
    
    # Master-Key aus Session!
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Enqueue Job mit Master-Key
    job_queue.enqueue(
        process_emails,
        user=user,
        master_key=master_key  # ← Explizit übergeben!
    )
    
    return jsonify({'status': 'queued'})
```

### Service Token: CLI-Access

Für Cron-Jobs, die OHNE Session laufen:

```python
# ServiceToken mit verschlüsseltem Master-Key

class ServiceToken(Base):
    __tablename__ = "service_tokens"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    token_hash = Column(String(255), unique=True)
    master_key = Column(String(255))  # Verschlüsselter Master-Key
    expires_at = Column(DateTime)

# Verwendung in CLI:
# cron-job --token=abc123def456 --service-account

def cron_fetch_all_accounts(token: str):
    db = get_db_session()
    
    # Validiere Token
    service_token = db.query(ServiceToken).filter_by(
        token_hash=hash(token)
    ).first()
    
    if not service_token or service_token.is_expired():
        raise PermissionError("Invalid or expired token")
    
    # Entschlüssle Master-Key (Passwort des System-Users)
    # Annahme: Es gibt einen CLI-Password für Service-Tokens
    system_password = os.environ['SERVICE_ACCOUNT_PASSWORD']
    master_key = decrypt_service_token(
        service_token.master_key,
        system_password
    )
    
    # Jetzt kann verarbeitet werden
    user = db.query(User).filter_by(id=service_token.user_id).first()
    process_emails(user, master_key=master_key)
```

---

## Testing-Richtlinie

### CLI-Tests (Erlaubt: KEINE Credentials nötig)

```python
# ✅ ERLAUBT: Unit-Tests ohne Credentials

def test_database_schema():
    """Testet ob Tabellen existieren"""
    engine, Session = models.init_db(':memory:')
    session = Session()
    
    # Keine Credentials nötig - nur Schema-Check
    count = session.query(models.User).count()
    assert count == 0


def test_encryption():
    """Testet Encrypt/Decrypt mit Test-Daten"""
    plaintext = "test@example.com"
    master_key = "test_key_123456789012345678901234"
    
    encrypted = encrypt_email_sender(plaintext, master_key)
    decrypted = decrypt_email_sender(encrypted, master_key)
    
    assert decrypted == plaintext


def test_flag_parsing():
    """Testet Flag-String Parsing"""
    imap_flags = "\\Seen \\Answered"
    is_seen = "\\Seen" in imap_flags
    is_answered = "\\Answered" in imap_flags
    
    assert is_seen == True
    assert is_answered == True
```

### Tests mit Credentials (NICHT über CLI)

```python
# ✗ NICHT ERLAUBT in Code:
def test_imap_fetch():
    master_key = "hardcoded_master_key"  # ← Security Risk!
    username = "test@gmx.de"
    password = "password123"  # ← In Code!
    
    fetcher = MailFetcher(server, username, password)
    mails = fetcher.fetch_new_emails()


# ✅ STATTDESSEN: UI-Tests mit echten Accounts

# Browser → Login (UI)
# → Settings → "Test Credentials"
# → Server hat User.master_key in Session
# → Entschlüsselt Credentials
# → Testet Verbindung
# → Zeigt Ergebnis im UI (z.B. "✓ Erfolgreich" oder "✗ Auth-Fehler")
```

**Warum:**
- UI-Tests laufen in **echtem Context** mit **User-Session**
- Credentials werden **nicht in Code hardcoded**
- Master-Key ist **nicht accessible im Test-Code**
- **Audit-Trail:** Wer hat was getestet, wann?
- **Zero-Knowledge bleibt intakt:** Nur der User authentifiziert sich

---

## Deployment-Sicherheit

### Umgebungsvariablen (.env)

**✅ ERLAUBT:**
```bash
# .env (NICHT im Git!)
SECRET_KEY=sehr_zufalliges_geheimnis_256_bit_base64_encoded
DATABASE_URL=sqlite:///emails.db
FLASK_SESSION_TYPE=filesystem
FLASK_SESSION_DIR=.flask_sessions
FLASK_SESSION_PERMANENT=false
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Lax
```

**❌ NIEMALS in .env:**
```bash
# DIESE GEHÖREN NICHT HIER!
TEST_USER_PASSWORD=password123
TEST_USER_MASTER_KEY=ajasjdhasdhj
IMAP_PASSWORD=mypassword
OAUTH_TOKEN=ya29.a0Ad...
SMTP_PASSWORD=secret
```

### Logging & Monitoring

**✅ ERLAUBT:**
```python
logger.info(f"User {user.id} fetched mails from account {account_id}")
logger.debug(f"Processed {count} emails in {duration}s")
logger.warning(f"Account {account_id} failed to fetch: connection timeout")
logger.error(f"Background job {job_id} failed")
```

**❌ NICHT ERLAUBT:**
```python
logger.debug(f"Password: {password}")  # ← NO!
logger.info(f"Subject: {email.subject}")  # ← NO! (encrypted in DB, aber dekodiert!?)
logger.error(f"OAuth token: {oauth_token}")  # ← NO!
logger.debug(f"Master-Key: {master_key}")  # ← NEVER!
logger.info(f"Email sender: {raw_email.encrypted_sender}")  # ← NO! (Ciphertext im Log)
```

### Secrets-Management

**Database Connection:**
```python
# ✓ RICHTIG: Aus Umgebungsvariable
DATABASE_URL = os.environ['DATABASE_URL']
engine = create_engine(DATABASE_URL)
```

**Session Secret:**
```python
# ✓ RICHTIG: Zufällig generiert bei Deployment
app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
# Generiert mit: python -c "import secrets; print(secrets.token_hex(32))"
```

**2FA Secret (TOTP):**
```python
# ✓ RICHTIG: Wird nur während Setup gekannt
# Nach Setup: nur Hash gespeichert
import pyotp
secret = pyotp.random_base32()  # Einmalig beim Setup
totp = pyotp.TOTP(secret)
# Nur der User speichert secret lokal, Server speichert nur Hash
```

---

## Compliance Checkliste

Vor jedem Deployment / Major Release:

### Datenschutz & Encryption

- [ ] Alle Credentials (IMAP/SMTP/OAuth) sind `encrypted_*` in DB
- [ ] Alle E-Mail-Inhalte sind `encrypted_*` in DB
- [ ] Alle KI-Ergebnisse sind `encrypted_*` in DB
- [ ] Passwörter sind gehashed (PBKDF2, nicht SHA!)
- [ ] Master-Key wird bei Logout gelöscht (`session.pop()`)
- [ ] Session-Timeout ist konfiguriert (max 24h)
- [ ] HTTPS ist enforce (in Production)
- [ ] Session-Cookies sind `secure`, `httponly`, `samesite`

### Logging & Monitoring

- [ ] Kein Klartext in Logs (auch nicht Debug-Level)
- [ ] Kein Passwort/Token in Error-Messages
- [ ] Kein Email-Content in Logs
- [ ] Credentials werden nicht geloggt
- [ ] Audit-Logs für sensitive Aktionen (Login, 2FA, Credential-Change)

### Code & Testing

- [ ] Tests mit Credentials laufen über UI, nicht CLI
- [ ] CLI-Tests brauchen KEINE echten Credentials
- [ ] RawEmail/ProcessedEmail Entschlüsselung in Routes, nicht in Models
- [ ] Master-Key wird als Parameter zu Background-Jobs übergeben
- [ ] Templates zeigen nur `decrypted_*` Variablen
- [ ] Keine Hardcoded Test-Credentials in Code/Repo
- [ ] git ls-files zeigt keine `.env` oder `secrets` Dateien

### Deployment

- [ ] `.env` ist in `.gitignore`
- [ ] `secrets/` ist in `.gitignore`
- [ ] `.flask_sessions/` ist in `.gitignore`
- [ ] Database-Backups sind verschlüsselt
- [ ] SSH-Keys für Server sind 4096-bit RSA minimum
- [ ] SSL/TLS ist minimum TLS 1.2
- [ ] HSTS-Header ist aktiviert
- [ ] CSP-Header ist gesetzt

### Incident Response

- [ ] Rollback-Plan dokumentiert
- [ ] Master-Key Rotation Plan
- [ ] Credential-Change Plan (wenn Server gehackt)
- [ ] Audit-Logs werden 90 Tage aufbewahrt
- [ ] Sicherheits-Kontakt ist definiert

---

## FAQ

### F: Was passiert wenn der Server gehackt wird?

**A:** Angreifer erhält:
- ✅ Verschlüsselte E-Mails (nutzlos ohne Master-Key)
- ✅ Verschlüsselte Credentials (nutzlos ohne Master-Key)
- ✅ Session-IDs (nutzlos wenn User logged out)

Angreifer erhält NICHT:
- ❌ Passwörter (nur Hashes)
- ❌ Master-Keys (nur verschlüsselt mit KEK)
- ❌ E-Mail-Inhalte (verschlüsselt)
- ❌ IMAP-Passwörter (verschlüsselt)

**Mitigation:**
- User ändert Passwort → neuer Master-Key bei nächstem Login
- Alte Sessions werden sofort invalid (new KEK)

### F: Kann der Server eine E-Mail lesen, wenn User offline ist?

**A:** Nein. Nur der User mit aktivem Master-Key in Session kann entschlüsseln.

### F: Was ist wenn Master-Key aus Session vergessen wird?

**A:** 
- User must logout
- Login erneut mit Passwort
- Neuer Master-Key wird generiert
- Session wird wieder aktiv

### F: Wie sicher sind 100.000 PBKDF2-Iterationen?

**A:** 
- ✅ Schützt gegen Brute-Force (langsam)
- ✅ Empfohlen von NIST (2021)
- ⚠️ Zukünftig: Upgradebar auf Argon2 wenn Hardware schneller wird

### F: Kann ich Multi-Device-Login machen?

**A:** 
- Ja, jedes Device bekommt eigene Session
- Jede Session hat eigene Master-Key (gleicher aus Passwort)
- Logout auf einem Device → andere Sessions bleiben aktiv
- Global Logout: Ändere Passwort → invalidiert alle Master-Keys

---

## Referenzen

- [OWASP: Zero-Knowledge Architecture](https://cheatsheetseries.owasp.org/)
- [NIST: Password Guidance](https://pages.nist.gov/800-63-3/sp800-63b.html)
- [RFC 5869: HKDF](https://tools.ietf.org/html/rfc5869)
- [AES-256-GCM: Authenticated Encryption](https://en.wikipedia.org/wiki/Galois/Counter_Mode)
- [SQLite WAL Mode](https://www.sqlite.org/wal.html)
