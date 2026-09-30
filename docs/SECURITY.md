# 🔐 KI-Mail-Helper – Security

**Version:** 2.0.0 (Multi-User Edition)  
**Stand:** August 2026

---

## Übersicht

KI-Mail-Helper implementiert **Zero-Knowledge at rest**: Mail-Inhalte und Credentials liegen in PostgreSQL verschlüsselt (DEK/AES-GCM). Der Server kann Klartext nur entschlüsseln, solange der Nutzer eingeloggt ist (DEK in Session-RAM bzw. Session-Dateien).

Siehe [Abschnitt 14 – Threat Model](#14-threat-model) für ehrliche Grenzen (Session-DEK, ServiceTokens, Cloud-PII).

---

## 1. Zero-Knowledge Encryption

### Schlüssel-Hierarchie

```
┌─────────────────────────────────────────────────────────────────┐
│  USER PASSWORD                                                   │
│       │                                                          │
│       ▼ PBKDF2-HMAC-SHA256 (600.000 Iterationen)                │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  KEK (Key Encryption Key)                                   │ │
│  │  • Abgeleitet aus Passwort                                  │ │
│  │  • Existiert nur in RAM (Session)                           │ │
│  └─────────────────────────────────────────────────────────────┘ │
│       │                                                          │
│       ▼ AES-256-GCM Entschlüsselung                             │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  DEK (Data Encryption Key)                                  │ │
│  │  • Verschlüsselt in DB gespeichert (encrypted_dek)          │ │
│  │  • Entschlüsselt nur in RAM                                 │ │
│  └─────────────────────────────────────────────────────────────┘ │
│       │                                                          │
│       ▼ AES-256-GCM Entschlüsselung                             │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  KLARTEXT-DATEN                                             │ │
│  │  • Emails (Subject, Body, Sender, etc.)                     │ │
│  │  • Credentials (IMAP/SMTP Server, Passwörter)               │ │
│  │  • AI-Ergebnisse (Zusammenfassungen, Kategorien)            │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### DEK/KEK Pattern - Vorteile

| Szenario | Ohne DEK/KEK | Mit DEK/KEK |
|----------|--------------|-------------|
| **Passwort ändern** | Alle Daten neu verschlüsseln | Nur DEK neu verschlüsseln |
| **10.000 Emails** | 10.000 Re-Encryptions | 1 Re-Encryption |
| **Dauer** | Minuten bis Stunden | < 1 Sekunde |

### Verschlüsselte Felder

**User:**
- `encrypted_dek` – Data Encryption Key

**MailAccount:**
- `encrypted_email`, `encrypted_imap_server`, `encrypted_imap_username`
- `encrypted_imap_password`, `encrypted_smtp_server`, `encrypted_smtp_username`
- `encrypted_smtp_password`, `encrypted_signature_text`

**RawEmail:**
- `encrypted_subject`, `encrypted_sender`, `encrypted_body`
- `encrypted_to`, `encrypted_cc`, `encrypted_bcc`
- `encrypted_message_id`, `encrypted_in_reply_to`, `encrypted_references`
- `encrypted_subject_sanitized`, `encrypted_body_sanitized`
- `encrypted_entity_map`
- `encrypted_inline_attachments` – Base64-encoded CID-Bilder als JSON

**ProcessedEmail:**
- `encrypted_summary`, `encrypted_translation`, `encrypted_zusammenfassung`
- `encrypted_reply_draft`

---

## 2. Authentifizierung

### Passwort-Anforderungen

```python
MIN_PASSWORD_LENGTH = 24  # OWASP Empfehlung
PASSWORD_REQUIREMENTS = {
    "min_length": 24,
    "require_uppercase": True,
    "require_lowercase": True,
    "require_digit": True,
    "require_special": True,
    "forbidden_sequences": ["abc", "123", "qwerty", "password"]
}
```

### Passwort-Hashing

```python
# PBKDF2-HMAC-SHA256
iterations = 600_000  # OWASP 2023 Empfehlung
salt = os.urandom(16)
hash = hashlib.pbkdf2_hmac('sha256', password, salt, iterations)
```

### Zwei-Faktor-Authentifizierung (2FA)

- **Pflicht** für alle Benutzer
- **TOTP** (Time-based One-Time Password)
- **Algorithmus:** SHA-1, 30s Intervall, 6 Ziffern
- **10 Recovery Codes** bei Aktivierung

### Account Lockout

```python
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = 900  # 15 Minuten

# Atomarer Counter (Race-Condition-sicher)
UPDATE users SET failed_login_count = failed_login_count + 1
WHERE id = :user_id
RETURNING failed_login_count
```

---

## 3. Session-Management

### Server-Side Sessions

```python
SESSION_TYPE = "filesystem"  # Nicht im Cookie
SESSION_FILE_DIR = ".flask_sessions"  # chmod 700
SESSION_USE_SIGNER = True
PERMANENT_SESSION_LIFETIME = timedelta(minutes=60)  # via SESSION_LIFETIME_MINUTES
SESSION_COOKIE_SECURE = True      # Nur HTTPS
SESSION_COOKIE_HTTPONLY = True    # Kein JS-Zugriff
SESSION_COOKIE_SAMESITE = "Lax"   # CSRF-Schutz
```

**Wichtig:** Nach Login wird `session["master_key"]` (DEK) in der Filesystem-Session gespeichert. Wer Lesezugriff auf `.flask_sessions` oder Backups davon hat, kann den DEK extrahieren. Das ist kein DB-Zero-Knowledge-Szenario, sondern Host-/Backup-Kompromittierung.

### Session-Timeout

- Konfigurierbar über `SESSION_LIFETIME_MINUTES` (Standard: 60 Minuten)
- Nach Timeout: erneuter Login + DEK aus Passwort

---

## 4. Rate Limiting

### Flask-Limiter Konfiguration

```python
# Keine globalen Default-Limits — nur explizit gesetzte Endpoints
default_limits = []

# Auth-Endpoints (in app_factory.py nach Limiter-Init)
limiter.limit("5 per minute")(login)
limiter.limit("3 per minute")(register)
limiter.limit("5 per minute")(verify_2fa)
```

Zusätzlich empfohlen: nginx `limit_req` auf dem Reverse Proxy (CT 108).

---

## 5. Input Validation

### SQL Injection Prevention

```python
# ✅ Parameterized Queries (SQLAlchemy)
user = User.query.filter_by(username=username).first()

# ❌ NIEMALS String-Interpolation
# cursor.execute(f"SELECT * FROM users WHERE name = '{username}'")
```

### XSS Prevention

```python
# Jinja2 Auto-Escaping (Standard)
{{ user_input }}  # Automatisch escaped

# Nur wenn explizit sicher
{{ trusted_html | safe }}

# JavaScript: escapeHtml() für alle User-Daten
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
```

### Input Length Limits

```python
# User Model
username: 3-80 Zeichen
email: 1-255 Zeichen
password: 24-255 Zeichen

# Email Sanitization
MAX_INPUT_LENGTH = 500_000  # 500 KB (DoS-Schutz)
```

---

## 6. ReDoS Protection

### Timeout-Decorator

```python
import signal

def with_timeout(seconds):
    def decorator(func):
        def handler(signum, frame):
            raise TimeoutError("Operation timed out")
        
        def wrapper(*args, **kwargs):
            signal.signal(signal.SIGALRM, handler)
            signal.alarm(seconds)
            try:
                return func(*args, **kwargs)
            finally:
                signal.alarm(0)
        return wrapper
    return decorator

@with_timeout(2)  # Max 2 Sekunden
def sanitize_email(content): ...
```

### Sichere Regex-Patterns

```python
# ❌ Katastrophales Backtracking
r'^Am .* schrieb .*:'

# ✅ Bounded + Non-Greedy
r'^Am .{1,200}? schrieb .{1,200}?:'

# ❌ Nested Quantifiers
r'\b[A-Za-z0-9._%+-]+\s*@\s*[A-Za-z0-9.-]+\s*\.\s*[A-Z|a-z]{2,}\b'

# ✅ RFC 5321 Compliant
r'[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,10}'
```

---

## 7. HTTPS & Headers

### Security Headers

```python
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; ..."
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response
```

### Content Security Policy

```
default-src 'self';
script-src 'self' 'nonce-{random}';
style-src 'self' 'unsafe-inline';
img-src 'self' data:;
font-src 'self';
connect-src 'self';
frame-ancestors 'none';
form-action 'self';
base-uri 'self';
```

---

## 8. Multi-User Isolation

### Datenbank-Ebene

```python
# Alle Queries mit User-Filter
emails = RawEmail.query.filter_by(user_id=current_user.id).all()

# Foreign Keys mit CASCADE DELETE
class MailAccount(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
```

### Ownership Validation

```python
def get_email_or_404(email_id):
    email = RawEmail.query.get_or_404(email_id)
    if email.user_id != current_user.id:
        abort(403)  # Forbidden
    return email
```

---

## 9. Logging & Monitoring

### Sensitive Data Masking

```python
# ❌ User-IDs im Log
logger.info(f"User {user.id} logged in")

# ✅ Maskierte IDs
logger.info(f"User {hash(user.id)[:8]}... logged in")

# ❌ Exception Details
logger.error(f"Error: {str(exception)}")

# ✅ Nur Exception-Typ
logger.error(f"Error: {type(exception).__name__}")
```

### Audit Trail

```python
# Login-Versuche
- Timestamp
- Username (erfolgreiche Logins)
- IP-Adresse
- User-Agent
- Erfolg/Misserfolg
```

---

## 10. Backup & Recovery

### Datenbank-Backup

```bash
# PostgreSQL Dump (verschlüsselte Daten!)
pg_dump -U mail_helper mail_helper | gzip > backup_$(date +%Y%m%d).sql.gz

# Nur verschlüsselte Daten werden gesichert
# Ohne User-Passwort sind Backups nutzlos (Zero-Knowledge)
```

### Recovery Codes

- 10 Einmal-Codes bei 2FA-Aktivierung
- Jeder Code nur einmal verwendbar
- Sicher aufbewahren (z.B. Passwort-Manager)

---

## 11. Betroffenheitsanalyse: Autofill-Clickjacking bei Passwort-Managern (ETH Zürich, Feb. 2026)

### Was wurde gefunden

Sicherheitsforscher der ETH Zürich haben in cloudbasierten Passwort-Manager-Erweiterungen (u. a. **LastPass, Bitwarden, Dashlane**) Lücken im Autofill-Mechanismus gefunden. Eine bösartige Webseite kann per DOM-Manipulation (unsichtbare/überlagerte Formularfelder, Clickjacking-Prinzip) den Browser-Passwort-Manager dazu bringen, gespeicherte Zugangsdaten automatisch in versteckte Felder einzutragen – die Seite liest sie anschließend per JavaScript aus. Die Lücke liegt in den **Browser-Extensions der Passwort-Manager**, nicht auf der Zielseite selbst; die Zielseite (bzw. eine darauf eingeschleuste bösartige Komponente) ist aber die Angriffsfläche, über die der Trick ausgeführt wird. Die betroffenen Anbieter haben die Lücken laut Artikel mittlerweile größtenteils geschlossen.

### Wie stark ist KI-Mail-Helper betroffen

Die Schwachstelle steckt in den Passwort-Manager-Erweiterungen selbst, nicht in unserem Code – wir können sie nicht patchen. Relevant für uns ist nur, ob **unsere Formulare** (Login, Registrierung, Passwort ändern, IMAP/SMTP-Zugangsdaten) als Einfallstor für den Trick missbraucht werden könnten. Prüfergebnis:

| Prüfpunkt | Befund | Bewertung |
|---|---|---|
| Versteckte/überlagerte Passwortfelder (`display:none`, `opacity:0`) in `login.html`, `register.html`, `change_password.html`, `add_mail_account.html`, `edit_mail_account.html` | Keine gefunden – alle `type="password"`-Felder sind sichtbar und einzeln | ✅ kein Angriffsmuster vorhanden |
| Voraussetzung für den Angriff auf eigener Seite: injizierbares HTML/JS (XSS) | `Content-Security-Policy` mit `script-src 'self' 'nonce-{random}'`, Jinja2 Auto-Escaping, `frame-ancestors 'none'` ([`app_factory.py`](../src/app_factory.py)) | ✅ deutlich erschwert |
| Clickjacking/Framing der eigenen Login-/Formularseiten durch fremde Seiten | `X-Frame-Options: DENY` + `frame-ancestors 'none'` | ✅ verhindert |
| `autocomplete`-Attribute auf Passwortfeldern | In allen relevanten Templates gesetzt (Login/Register: `username`/`current-password`/`new-password`; IMAP/SMTP: `off`) | ✅ umgesetzt |
| Eigene Speicherung der IMAP/SMTP-Zugangsdaten | Serverseitig AES-256-GCM verschlüsselt (Zero-Knowledge, siehe Abschnitt 1) – unabhängig vom Autofill des Browsers | ✅ nicht betroffen |

**Fazit:** Die direkte Angriffsfläche in unserer Anwendung ist gering – wir haben keine versteckten Formularfelder, eine harte CSP und Framing ist blockiert, was die Grundvoraussetzung des Angriffs (Code-Injection oder Framing der eigenen Seite) bereits verhindert. Ein Restrisiko besteht, falls Nutzer:innen einen ungepatchten Passwort-Manager verwenden und über eine *andere*, kompromittierte Webseite (nicht KI-Mail-Helper) angegriffen werden – das liegt außerhalb unserer Kontrolle.

### Maßnahmen

1. **Umgesetzt:** `autocomplete`-Attribute auf allen Formularen ergänzt – `login.html`/`register.html` (eigenes Konto) nutzen `username` / `current-password` / `new-password`. `add_mail_account.html`/`edit_mail_account.html` (fremde IMAP/SMTP-Zugangsdaten) nutzen bewusst `autocomplete="off"`.
2. **Bestehend beibehalten:** CSP mit Nonce, `X-Frame-Options: DENY`/`frame-ancestors 'none'` und Jinja2 Auto-Escaping.
3. **Review-Regel:** Bei neuen Templates keine `type="password"`-Felder mit `display:none`/`opacity:0`/`visibility:hidden` oder außerhalb des sichtbaren Viewports platzieren.
4. **Nutzerkommunikation:** Passwort-Manager-Erweiterungen zeitnah aktualisieren.
5. **Kein Handlungsbedarf** bei der Zero-Knowledge-Verschlüsselung der IMAP/SMTP-Credentials.

---

## 12. Härtungs-Roadmap

### 12.1 Behobene Lücken (dieser Patch)

| Finding | Problem | Fix |
|---|---|---|
| **SECRET_KEY-Mismatch** | `00_env_validator.py` erzwang beim Start `FLASK_SECRET_KEY`, aber `app_factory.py` las nur `SECRET_KEY` und fiel sonst auf den hartkodierten String `"dev-secret-key-change-in-production"` zurück. Wer nur `FLASK_SECRET_KEY` gesetzt hat (wie vom Validator verlangt), lief unbemerkt mit dem öffentlich bekannten Default-Key – CSRF-Tokens und signierte Session-Cookies wären fälschbar gewesen. | `app_factory.py` liest jetzt `SECRET_KEY` **oder** `FLASK_SECRET_KEY`; fehlen beide, wird beim Start ein zufälliger Ephemeral-Key erzeugt (mit Warnung) statt des statischen Default-Strings. |
| **Ungesignte Session-IDs** | `SESSION_USE_SIGNER = False` – die im Cookie gespeicherte Session-ID war nicht mit `SECRET_KEY` signiert. | `SESSION_USE_SIGNER = True` gesetzt – die Session-ID wird jetzt zusätzlich signiert. |

### 12.2 Offene Empfehlungen (nicht in diesem Patch umgesetzt)

| Empfehlung | Begründung | Aufwand |
|---|---|---|
| **PBKDF2 → Argon2id** für KEK-Ableitung | Argon2id ist memory-hard und resistenter gegen GPU/ASIC-Offline-Cracking als PBKDF2-HMAC-SHA256. | Mittel – Migration bestehender User beim nächsten Login. |
| **CSP `img-src`** enger fassen | `img-src 'self' data: https:;` erlaubt Tracking-Pixel aus jeder HTTPS-Quelle. | Niedrig, ggf. Funktionsänderung für Remote-Bilder in Mails. |
| **DEK-Exposure in Server-Session** | `session["master_key"]` liegt unverschlüsselt in `.flask_sessions`. | Mittel – kürzere Session-TTL, verschlüsseltes Session-Backend, oder DEK nur im RAM. |
| **2FA schützt nicht die Verschlüsselung** | TOTP gated nur den Login, fließt nicht in die KEK-Ableitung ein. | Siehe 12.3 (Secret-Key-Ansatz). |

### 12.3 1Password-Ansatz: Secret Key einbringen

**Warum:** Ein einziges Geheimnis (Passwort) treibt die Schlüsselkette; 2FA verhindert Offline-Entschlüsselung nicht. Ein zweiter, nie übertragener **Secret Key** (128 Bit) schließt diese Lücke analog zu 1Password.

**Design (kompatibel mit bestehendem DEK/KEK-Pattern):**

```
User Password + Secret Key (128 Bit, nur clientseitig/beim User)
              │
    PBKDF2/Argon2id(password || secret_key, salt)
              │
              ▼
             KEK → AES-256-GCM → DEK → Daten (wie bisher)
```

- **Registrierung:** Secret Key einmalig generieren/anzeigen, nirgends in DB speichern.
- **KDF:** `generate_master_key(password + secret_key, salt)`.
- **Login-UX:** Secret Key mit Passwort abfragen; auf vertrauenswürdigen Geräten optional lokal speichern.
- **Recovery:** Verlust = Datenverlust (Zero-Knowledge-Tradeoff).
- **Migration:** Analog zum `encrypted_master_key`-Deprecation-Pattern beim nächsten Login.

**Einordnung:** Größte architektonische Änderung in dieser Liste – als eigenes Vorhaben planen.

---

## 13. Bekannte Limitierungen

| Limitierung | Beschreibung | Mitigation |
|-------------|--------------|------------|
| **Passwort-Verlust** | Daten unwiederbringlich | Recovery Codes, Dokumentation |
| **RAM-/Session-Exposure** | DEK in RAM und `.flask_sessions` | Kurze Session-TTL, Server-Hardening, verschlüsselte Backups |
| **ServiceToken DEK** | Celery-Token speichern DEK plaintext in DB (TTL) | Kurze TTL, Löschung bei Logout, kein DB-Dump während aktiver Tokens |
| **TOTP-Secret** | `totp_secret` in DB unverschlüsselt | DB-Zugriff = 2FA bypass möglich; Postgres nur localhost |
| **Timing Attacks** | Login-Enumeration erschwert | Dummy-Hash bei unbekanntem User |
| **Brute Force** | Passwort-Raten | Rate Limiting (Login/2FA), Account Lockout |
| **Celery Flower** | Task-Results können PII enthalten | **Nicht** in Produktion deployen (nur Dev, localhost) |

---

## 14. Security Checklist für Deployment

- [ ] `SECRET_KEY` gesetzt (nicht leer)
- [ ] `BEHIND_REVERSE_PROXY=true` hinter nginx
- [ ] HTTPS mit gültigem Zertifikat (Let's Encrypt)
- [ ] Reverse Proxy (Nginx/Caddy) mit Rate Limiting
- [ ] Firewall: App-Port nur vom Reverse Proxy (UFW auf App-CT)
- [ ] PostgreSQL: Nur localhost, kein Remote-Zugriff
- [ ] Redis: Nur localhost, kein Remote-Zugriff
- [ ] **Kein** Flower/Celery-UI öffentlich
- [ ] Regelmäßige Backups (verschlüsselte DB — ohne Passwort nutzlos)
- [ ] Log-Rotation konfiguriert
- [ ] Automatische Security-Updates (unattended-upgrades)
- [ ] Secrets nicht in Git (.env in .gitignore)

---

## 15. Vulnerability Reporting

Falls du eine Sicherheitslücke findest:

1. **Nicht** öffentlich melden (kein GitHub Issue)
2. Kontaktiere den Maintainer direkt
3. Beschreibe die Lücke detailliert
4. Warte auf Bestätigung bevor du veröffentlichst

---

## 16. Threat Model

### Was ist geschützt?

| Angriffsszenario | Geschützt? | Mechanismus |
|------------------|------------|-------------|
| DB-Dump ohne Login | **Ja** (Mail-Inhalte) | AES-GCM, DEK mit PBKDF2 aus Passwort |
| Anderer User sieht meine Mails | **Ja** | `user_id`-Filter auf allen Queries |
| Brute-Force Login | **Teilweise** | 2FA, Lockout, IP Rate-Limits |
| Cloud-Provider sieht Roh-PII | **Ja** (wenn konfiguriert) | Anonymisierung fail-closed für Cloud |
| Fremde Celery-Task-ID abfragen | **Ja** | Task-Ownership in Redis + Metadaten |

### Was ist nicht vollständig geschützt?

| Szenario | Risiko | Hinweis |
|----------|--------|---------|
| Host root auf App-Server | Hoch | `.flask_sessions` enthält DEK |
| DB-Dump + aktiver ServiceToken | Hoch | `encrypted_dek`-Spalte = plaintext DEK (TTL) |
| Kompromittierte Session-Cookie | Hoch | Wie eingeloggter User |
| Mail-HTML Tracking/Phishing | Mittel | CSP/Sandbox, kein HTML-Sanitizer |

### ServiceToken (Celery)

Background-Tasks benötigen den DEK ohne Flask-Session. Dafür werden kurzlebige `service_tokens` mit **plaintext DEK** in der DB gespeichert (Spaltenname historisch `encrypted_dek`). Tokens werden beim Logout gelöscht.

### Produktion vs. Entwicklung

| Komponente | Produktion (CT 134) | Entwicklung |
|------------|---------------------|-------------|
| Gunicorn + Celery Worker + Beat | ✅ | ✅ |
| Flower (Port 5555) | ❌ nicht deployen | nur `127.0.0.1` + Auth |

---

*Dieses Dokument beschreibt die Sicherheitsarchitektur von KI-Mail-Helper v2.0 (Multi-User Edition).*
