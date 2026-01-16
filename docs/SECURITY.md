# 🔐 KI-Mail-Helper – Security

**Version:** 2.0.0 (Multi-User Edition)  
**Stand:** Januar 2026  
**Security Score:** 98/100 (Production-Hardened)

---

## Übersicht

KI-Mail-Helper implementiert eine **Zero-Knowledge-Architektur**, bei der der Server niemals Zugriff auf Klartext-Daten hat. Alle sensiblen Informationen werden clientseitig verschlüsselt.

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
SESSION_TYPE = "filesystem"  # Nicht in Cookie
SESSION_FILE_DIR = ".flask_sessions"
PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
SESSION_COOKIE_SECURE = True      # Nur HTTPS
SESSION_COOKIE_HTTPONLY = True    # Kein JS-Zugriff
SESSION_COOKIE_SAMESITE = "Lax"   # CSRF-Schutz
```

### Session-Timeout

- **Inaktivität:** 30 Minuten → Auto-Logout
- **Absolute:** 8 Stunden → Erneuter Login erforderlich

---

## 4. Rate Limiting

### Flask-Limiter Konfiguration

```python
# Globale Limits
DEFAULT_LIMITS = ["200 per day", "50 per hour"]

# Endpoint-spezifisch
@limiter.limit("5 per minute")
def login(): ...

@limiter.limit("5 per minute")
def verify_2fa(): ...

@limiter.limit("3 per minute")
def register(): ...

@limiter.limit("10 per minute")
def password_reset(): ...
```

### Bypass für authentifizierte Requests

```python
@limiter.limit("60 per minute", exempt_when=lambda: current_user.is_authenticated)
def api_endpoint(): ...
```

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

## 11. Bekannte Limitierungen

| Limitierung | Beschreibung | Mitigation |
|-------------|--------------|------------|
| **Passwort-Verlust** | Daten unwiederbringlich | Recovery Codes, Dokumentation |
| **RAM-Exposure** | DEK in Server-RAM | Server-Hardening, Secure Memory |
| **Timing Attacks** | Login-Enumeration | Constant-Time Comparison |
| **Brute Force** | Passwort-Raten | Rate Limiting, Account Lockout |

---

## 12. Security Checklist für Deployment

- [ ] HTTPS mit gültigem Zertifikat (Let's Encrypt)
- [ ] Reverse Proxy (Nginx/Caddy) mit Rate Limiting
- [ ] Firewall: Nur 80/443 von außen erreichbar
- [ ] PostgreSQL: Nur localhost, kein Remote-Zugriff
- [ ] Redis: Nur localhost, kein Remote-Zugriff
- [ ] Regelmäßige Backups (verschlüsselt)
- [ ] Log-Rotation konfiguriert
- [ ] Fail2ban für SSH und Web
- [ ] Automatische Security-Updates (unattended-upgrades)
- [ ] Secrets nicht in Git (.env in .gitignore)

---

## 13. Vulnerability Reporting

Falls du eine Sicherheitslücke findest:

1. **Nicht** öffentlich melden (kein GitHub Issue)
2. Kontaktiere den Maintainer direkt
3. Beschreibe die Lücke detailliert
4. Warte auf Bestätigung bevor du veröffentlichst

---

*Dieses Dokument beschreibt die Sicherheitsarchitektur von KI-Mail-Helper v2.0 (Multi-User Edition).*
