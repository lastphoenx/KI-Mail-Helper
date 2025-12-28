# Multi-Auth Architecture - KI-Mail-Helper

## 📐 Architektur-Übersicht

Das KI-Mail-Helper System unterstützt **drei parallele Authentifizierungsmethoden** für E-Mail-Konten:

```
┌─────────────────────────────────────────────────┐
│           MailAccount (Database)                │
│  ┌───────────────────────────────────────────┐  │
│  │ auth_type: Enum("imap", "oauth", "pop3")  │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   ┌────────┐   ┌────────┐   ┌────────┐
   │  IMAP  │   │ OAuth  │   │  POP3  │
   └────────┘   └────────┘   └────────┘
        │             │             │
        ▼             ▼             ▼
   MailFetcher  GoogleMail-  POP3Mail-
   (06_*.py)    Fetcher      Fetcher
                (10_*.py)    (07_*.py)
```

---

## 🏗️ Database Schema

### MailAccount Model

```python
class MailAccount(Base):
    # Allgemein
    auth_type: str  # "imap" | "oauth" | "pop3"
    name: str
    enabled: bool
    
    # IMAP-spezifisch
    imap_server: str
    imap_port: int
    imap_username: str
    encrypted_imap_password: bytes
    
    # OAuth-spezifisch
    oauth_provider: str  # "google" | "microsoft"
    encrypted_oauth_token: bytes
    encrypted_oauth_refresh_token: bytes
    oauth_expires_at: datetime
    
    # POP3-spezifisch
    pop3_server: str
    pop3_port: int
    pop3_username: str
    encrypted_pop3_password: bytes
    
    # SMTP (optional, für Versand)
    smtp_server: str
    smtp_port: int
    encrypted_smtp_password: bytes
```

---

## 🔧 Factory Pattern

Die `get_mail_fetcher_for_account()` Funktion in `src/06_mail_fetcher.py` wählt den richtigen Fetcher basierend auf `auth_type`:

```python
def get_mail_fetcher_for_account(mail_account, master_key):
    """Gibt den richtigen Fetcher zurück"""
    
    # Validiere Felder
    is_valid, error = mail_account.validate_auth_fields()
    if not is_valid:
        raise ValueError(error)
    
    # Route basierend auf auth_type
    if mail_account.auth_type == "oauth":
        return GoogleMailFetcher(...)
    
    elif mail_account.auth_type == "imap":
        return MailFetcher(...)
    
    elif mail_account.auth_type == "pop3":
        return POP3MailFetcher(...)
```

---

## ✅ Validierung

Jeder Account wird vor dem Fetch validiert:

```python
account.validate_auth_fields()
# Returns: (bool, str)
# - True, ""  → Valid
# - False, "IMAP requires: server, username, password"  → Invalid
```

**Regeln:**
- **IMAP:** `imap_server`, `imap_username`, `encrypted_imap_password` müssen gesetzt sein
- **OAuth:** `oauth_provider`, `encrypted_oauth_token` müssen gesetzt sein
- **POP3:** `pop3_server`, `pop3_username`, `encrypted_pop3_password` müssen gesetzt sein

---

## 🔄 Migration

Existierende Accounts werden automatisch migriert:

```sql
-- Alembic Migration: 86ca02f07586_add_auth_type_and_pop3_support
UPDATE mail_accounts 
SET auth_type = CASE 
    WHEN oauth_provider IS NOT NULL THEN 'oauth'
    ELSE 'imap'
END;
```

---

## 📝 Verwendung in Background Jobs

```python
from src.models import Session, MailAccount
from src.mail_fetcher import get_mail_fetcher_for_account

session = Session()
account = session.query(MailAccount).filter_by(id=1).first()

# Master-Key vom User holen
master_key = get_user_master_key(account.user_id)

# Factory erstellt den richtigen Fetcher
fetcher = get_mail_fetcher_for_account(account, master_key)

# Einheitliche API für alle Auth-Typen
fetcher.connect()
emails = fetcher.fetch_new_emails(limit=50)
fetcher.disconnect()
```

---

## 🆕 Neue Auth-Methode hinzufügen

Um eine neue Auth-Methode (z.B. Exchange, DAV) hinzuzufügen:

### 1. Enum erweitern

```python
# src/02_models.py
class AuthType(str, Enum):
    IMAP = "imap"
    OAUTH = "oauth"
    POP3 = "pop3"
    EXCHANGE = "exchange"  # NEU
```

### 2. Felder hinzufügen

```python
# src/02_models.py - MailAccount
exchange_server = Column(String(255), nullable=True)
exchange_domain = Column(String(100), nullable=True)
encrypted_exchange_password = Column(Text)
```

### 3. Alembic Migration

```bash
alembic revision -m "add_exchange_support"
```

### 4. Fetcher implementieren

```python
# src/08_exchange_fetcher.py
class ExchangeMailFetcher:
    def connect(self): ...
    def fetch_new_emails(self): ...
    def disconnect(self): ...
```

### 5. Factory erweitern

```python
# src/06_mail_fetcher.py
elif mail_account.auth_type == "exchange":
    exchange = importlib.import_module('.08_exchange_fetcher', 'src')
    return exchange.ExchangeMailFetcher(...)
```

### 6. Validierung

```python
# src/02_models.py - MailAccount.validate_auth_fields()
elif self.auth_type == AuthType.EXCHANGE.value:
    if not all([self.exchange_server, self.exchange_domain, ...]):
        return False, "Exchange requires: server, domain, password"
```

---

## 📊 Vergleichstabelle

| Feature | IMAP | OAuth | POP3 |
|---------|------|-------|------|
| Empfangen | ✅ | ✅ | ✅ |
| Versenden | ✅ (SMTP) | ✅ | ❌ |
| Ordner | ✅ | ✅ | ❌ |
| UID-Tracking | ✅ | ✅ | ⚠️ (Message-ID) |
| Token-Refresh | ❌ | ✅ | ❌ |
| Server-Löschen | ❌ | ❌ | ⚠️ (optional) |
| Sicherheit | ⚠️ (App-Passwort) | ✅✅ | ⚠️ (Passwort) |

---

## 🔐 Security

Alle Credentials werden verschlüsselt:
- **Algorithm:** AES-256-GCM
- **Key Derivation:** PBKDF2 mit User-Master-Key
- **Storage:** `encrypted_imap_password`, `encrypted_oauth_token`, etc.

```python
from src.encryption import CredentialManager

# Encrypt
encrypted = CredentialManager.encrypt_imap_password(password, master_key)

# Decrypt
password = CredentialManager.decrypt_imap_password(encrypted, master_key)
```

---

## 📚 Dateien-Übersicht

```
src/
├── 02_models.py               # MailAccount Model mit auth_type
├── 06_mail_fetcher.py         # IMAP Fetcher + Factory
├── 07_pop3_fetcher.py         # POP3 Fetcher
├── 08_encryption.py           # CredentialManager
├── 10_google_oauth.py         # OAuth Manager + GoogleMailFetcher
└── 14_background_jobs.py      # Cron Jobs (nutzt Factory)

migrations/versions/
└── 86ca02f07586_*.py          # Migration für auth_type

docs/
└── OAUTH_AND_IMAP_SETUP.md    # User-Dokumentation
```

---

## 🧪 Testing

```bash
# IMAP Test
IMAP_SERVER=imap.gmx.net \
IMAP_USERNAME=user@gmx.net \
IMAP_PASSWORD=secret \
python -m src.06_mail_fetcher

# POP3 Test
POP3_SERVER=pop.gmx.net \
POP3_USERNAME=user@gmx.net \
POP3_PASSWORD=secret \
python -m src.07_pop3_fetcher

# OAuth Test (benötigt Token)
python test_google_oauth.py
```

---

## ✅ Vorteile dieser Architektur

1. **Erweiterbar:** Neue Auth-Methoden ohne Breaking Changes
2. **Typsicher:** Enum verhindert Tippfehler
3. **Validiert:** Felder werden vor Verwendung geprüft
4. **Einheitlich:** Alle Fetcher haben gleiche API
5. **Sicher:** Alle Credentials verschlüsselt
6. **Migrierbar:** Alembic verwaltet Schema-Änderungen

---

**Stand:** 2025-12-25 | **Version:** 2.0 (Multi-Auth)
