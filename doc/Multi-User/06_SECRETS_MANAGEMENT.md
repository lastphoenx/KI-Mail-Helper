# Secrets Management Strategie
## KI-Mail-Helper Multi-User Migration

**Status**: Produktionsreife Secrets-Verwaltung  
**Geschätzter Aufwand**: 3-4 Stunden  
**Datum**: Januar 2026  
**Sprache**: Deutsch  

---

## 🎯 ZIEL

Sichere Verwaltung von Secrets (Passwörter, API-Keys, Master-Keys) OHNE hardcoded Werte:
- ✅ `.env` File niemals in Produktiv-Umgebung nutzen
- ✅ DEK/EK (Database Encryption Key) nur im UI & sichere Backend
- ✅ Secrets in PostgreSQL verschlüsselt ablegen
- ✅ Rotation & Audit von Secrets

---

## ⚠️ PROBLEM: Wo landen die Passwörter?

Deine Fragen:
> Secrets-Management: Redis PW in .env - was ist genau das DB passwort (admin?) auch in .env

### Antwort:

```
┌─────────────────────────────────────────────────────────────────────┐
│ LOCAL DEVELOPMENT (.env)                                            │
├─────────────────────────────────────────────────────────────────────┤
│ DATABASE_URL=postgresql://admin:dev_password_123@localhost:5432/... │
│ REDIS_URL=redis://localhost:6379/0                                  │
│ ❌ OK nur für LOCAL DEV! Niemals in Produktion!                     │
└─────────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STAGING/PRODUCTION (SecureVault)                                    │
├─────────────────────────────────────────────────────────────────────┤
│ DATABASE_URL → Umgebungsvariable (systemd, K8s, AWS Systems Manager)│
│ REDIS_PASSWORD → Vault (HashiCorp Vault, AWS Secrets Manager, etc) │
│ ENCRYPTION_KEY → Hardware Security Module (HSM) oder Vault          │
│ ✅ Sicher! Kein Plaintext in Files!                                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Konkreter Stack:

```
Local Dev:
  - PostgreSQL: admin / dev_password (in .env.local)
  - Redis: kein Password (im Network isoliert)
  
Staging/Production:
  - PostgreSQL: Managed Service (AWS RDS, DigitalOcean, etc)
    → Password in AWS Secrets Manager
    → DATABASE_URL = Env-Var (nicht .env!)
  
  - Redis: Managed Service (AWS ElastiCache, Redis Cloud, etc)
    → Password in Vault
    → REDIS_PASSWORD = Env-Var
  
  - Encryption Keys (DEK/EK):
    → NICHT in Secrets Manager (nur für Rotation)
    → In Hardware Security Module (HSM) oder Vault
    → Oder: Im sichere UI-Dialog eingeben (User tippt ein)
```

---

## 🔐 SCHRITT 1: Local Development (.env)

### 1.1 `.env.local` für Entwicklung

```bash
# .env.local (NIEMALS committen!)
# Nur für lokale Entwicklung!

# ========== DATABASE ==========
DATABASE_URL=postgresql://dev_admin:dev_password_123@localhost:5432/mail_helper_dev

# ========== REDIS ==========
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=  # Local: kein Password nötig

# ========== CELERY ==========
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# ========== FEATURE FLAGS ==========
FLASK_ENV=development
USE_LEGACY_JOBS=true
USE_POSTGRESQL=true

# ========== SECRETS (NUR LOCAL!) ==========
SECRET_KEY=dev_secret_key_12345_do_not_use_in_production
ENCRYPTION_MASTER_KEY=dev_master_key_67890_never_in_production
```

### 1.2 `.env.example` (für Git)

```bash
# .env.example
# Kopiere zu .env.local und trage deine Werte ein!

DATABASE_URL=postgresql://user:password@localhost:5432/mail_helper
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

FLASK_ENV=development
USE_LEGACY_JOBS=true
USE_POSTGRESQL=true

SECRET_KEY=your_secret_key_here
ENCRYPTION_MASTER_KEY=your_encryption_key_here
```

### 1.3 `.gitignore` Update

```bash
# .gitignore (stelle sicher, dass .env files ignoriert sind!)

# Environment files
.env
.env.local
.env.*.local
.env.prod
.env.staging

# Secrets
secrets/
*.key
*.pem
credentials.json

# Python
__pycache__/
*.pyc
.pytest_cache/
htmlcov/

# IDE
.vscode/
.idea/
*.swp
```

---

## 🏭 SCHRITT 2: Production Secrets Management

### 2.1 Option A: Environment Variables (einfach, für kleine Deployments)

**Für: Single Server / VPS Hosting**

```bash
# Auf Production-Server (z.B. via SSH, nie per Email!)

# 1. Secrets in Systemd Service-Datei
sudo tee /etc/systemd/system/mail-helper.service > /dev/null << 'EOF'
[Unit]
Description=KI-Mail-Helper Multi-User
After=postgresql.service redis.service

[Service]
Type=notify
User=mail-helper
WorkingDirectory=/opt/mail-helper
Environment="DATABASE_URL=postgresql://prod_user:LONG_RANDOM_PASSWORD@db.example.com:5432/mail_prod"
Environment="REDIS_PASSWORD=REDIS_LONG_RANDOM_PASSWORD"
Environment="REDIS_URL=redis://:REDIS_LONG_RANDOM_PASSWORD@redis.example.com:6379/0"
Environment="SECRET_KEY=FLASK_SECRET_KEY_32_BYTES_RANDOM"
Environment="ENCRYPTION_MASTER_KEY=ENCRYPTION_KEY_32_BYTES_RANDOM"
Environment="FLASK_ENV=production"
Environment="USE_POSTGRESQL=true"
ExecStart=/opt/mail-helper/venv/bin/python3 -m src.00_main --serve --https --port 5003
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl start mail-helper
sudo systemctl enable mail-helper
```

**Vorteile:**
- ✅ Einfach für kleine Deployments
- ✅ Keine externe Abhängigkeit

**Nachteile:**
- ❌ Passwörter in systemd visible via `systemctl show`
- ❌ Keine zentrale Secrets-Verwaltung
- ❌ Keine Rotation

### 2.2 Option B: HashiCorp Vault (professionell, für größere Setups)

**Für: Multi-Server / Enterprise**

#### Installation

```bash
# Auf Vault Server:
curl https://releases.hashicorp.com/vault/1.15.1/vault_1.15.1_linux_amd64.zip > vault.zip
unzip vault.zip
sudo mv vault /usr/local/bin/

# Starte Vault
vault server -config=/etc/vault/config.hcl

# Initialisiere Vault (1x!)
vault operator init -key-shares=3 -key-threshold=2

# Unseal Vault (mit 2 der 3 Keys)
vault operator unseal KEY1
vault operator unseal KEY2

# Login
vault login -method=token TOKEN_FROM_INIT
```

#### Secrets speichern

```bash
# PostgreSQL Password in Vault
vault kv put secret/mail-helper/postgresql \
  host="db.example.com" \
  port="5432" \
  username="prod_user" \
  password="LONG_RANDOM_PASSWORD" \
  database="mail_prod"

# Redis in Vault
vault kv put secret/mail-helper/redis \
  host="redis.example.com" \
  port="6379" \
  password="REDIS_LONG_RANDOM_PASSWORD"

# Encryption Keys in Vault
vault kv put secret/mail-helper/encryption \
  master_key="ENCRYPTION_KEY_32_BYTES_RANDOM" \
  rotation_date="2026-03-01"
```

#### In Application nutzen

```python
# src/helpers/secrets.py
"""Load secrets from Vault."""

import os
import hvac
import logging

logger = logging.getLogger(__name__)

VAULT_ADDR = os.getenv("VAULT_ADDR", "http://localhost:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")

def get_vault_client():
    """Verbinde zu Vault."""
    if not VAULT_TOKEN:
        raise ValueError("VAULT_TOKEN nicht in Umgebung!")
    
    client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
    
    if not client.is_authenticated():
        raise ValueError("Vault authentication failed!")
    
    return client

def get_database_url():
    """Hole DATABASE_URL aus Vault."""
    client = get_vault_client()
    
    secret = client.secrets.kv.v2.read_secret_version(
        path="mail-helper/postgresql"
    )
    
    data = secret['data']['data']
    return f"postgresql://{data['username']}:{data['password']}@{data['host']}:{data['port']}/{data['database']}"

def get_redis_password():
    """Hole Redis Password aus Vault."""
    client = get_vault_client()
    
    secret = client.secrets.kv.v2.read_secret_version(
        path="mail-helper/redis"
    )
    
    return secret['data']['data']['password']

# In app_factory.py:
if os.getenv("VAULT_ENABLED", "false").lower() == "true":
    DATABASE_URL = get_database_url()
    REDIS_PASSWORD = get_redis_password()
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///...")
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
```

**requirements.txt:**
```bash
pip install hvac  # Vault Python Client
```

**Starte App mit Vault:**
```bash
export VAULT_ADDR=http://vault.example.com:8200
export VAULT_TOKEN=s.XXXXXXXXXXXXXXXX
export VAULT_ENABLED=true

python3 -m src.00_main --serve --https --port 5003
```

### 2.3 Option C: AWS Secrets Manager (für AWS-Deployments)

**Für: AWS Lambda / EC2 / ECS**

```python
# src/helpers/secrets.py (AWS Version)
"""Load secrets from AWS Secrets Manager."""

import json
import boto3
import logging

logger = logging.getLogger(__name__)

def get_secret(secret_name, region_name="eu-west-1"):
    """Hole Secret aus AWS Secrets Manager."""
    
    client = boto3.client("secretsmanager", region_name=region_name)
    
    try:
        response = client.get_secret_value(SecretId=secret_name)
    except client.exceptions.ResourceNotFoundException:
        logger.error(f"Secret '{secret_name}' not found in Secrets Manager!")
        raise
    
    if "SecretString" in response:
        return json.loads(response["SecretString"])
    else:
        return response["SecretBinary"]

def get_database_url():
    """Hole DATABASE_URL aus AWS."""
    secret = get_secret("mail-helper/postgresql")
    return f"postgresql://{secret['username']}:{secret['password']}@{secret['host']}/{secret['database']}"

def get_redis_password():
    """Hole Redis Password aus AWS."""
    secret = get_secret("mail-helper/redis")
    return secret["password"]

# In app_factory.py:
import os
if os.getenv("AWS_SECRETS", "false").lower() == "true":
    DATABASE_URL = get_database_url()
    REDIS_PASSWORD = get_redis_password()
```

**Starte App mit AWS:**
```bash
export AWS_REGION=eu-west-1
export AWS_SECRETS=true
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...

python3 -m src.00_main --serve --https --port 5003
```

---

## 🔐 SCHRITT 3: Encryption Keys Management (DEK/EK)

### 3.1 Problem: Wo lagern DEK/EK?

```
┌────────────────────────────────────────────────────────┐
│ FALSCH: In der Datenbank ❌                             │
├────────────────────────────────────────────────────────┤
│ DB-Dump + DEK in der gleichen DB =                    │
│ Angreifer hat DB-Dump + kann alles decryptieren!      │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│ RICHTIG: Getrennt von DB ✅                            │
├────────────────────────────────────────────────────────┤
│ Option 1: In Vault/AWS Secrets Manager                │
│ Option 2: Im UI (User tippt bei Startup ein)          │
│ Option 3: Hardware Security Module (HSM)              │
└────────────────────────────────────────────────────────┘
```

### 3.2 Lösung A: DEK aus Vault laden

```python
# src/helpers/encryption.py
"""Load encryption keys from Vault."""

import os
from src.helpers.secrets import get_vault_client

def get_encryption_key():
    """Lade DEK aus Vault zur Laufzeit."""
    
    if os.getenv("ENCRYPTION_KEY_SOURCE") == "vault":
        client = get_vault_client()
        secret = client.secrets.kv.v2.read_secret_version(
            path="mail-helper/encryption"
        )
        return secret['data']['data']['master_key']
    
    elif os.getenv("ENCRYPTION_KEY_SOURCE") == "env":
        # Fallback: Aus Env-Var (für systemd oder ähnlich)
        return os.getenv("ENCRYPTION_MASTER_KEY")
    
    else:
        raise ValueError("ENCRYPTION_KEY_SOURCE not set!")

# Beim App-Start:
# (Lagere nicht im Memory, sondern rufe on-demand auf)
```

### 3.3 Lösung B: DEK aus User-Input (für sehr sensible Szenarien)

```python
# src/helpers/encryption.py (User-Eingabe Version)
"""Encryption key from secure user input."""

import getpass
from cryptography.fernet import Fernet

_encryption_key = None

def get_encryption_key_from_user():
    """
    Frage Benutzer bei Startup nach DEK.
    
    Nur für lokale Deployments oder Interactive Mode!
    """
    global _encryption_key
    
    if _encryption_key is not None:
        return _encryption_key
    
    print("\n🔐 ENCRYPTION KEY REQUIRED")
    print("   Bitte gib den Master Encryption Key ein:")
    print("   (wird nicht echoed, max 60 Sekunden)")
    
    try:
        key_input = getpass.getpass("Master Key: ", stream=None)
        
        # Validiere: Muss 32 Bytes Base64 sein (Fernet)
        if len(key_input) != 44:  # Base64 encoded 32 bytes
            raise ValueError("Key muss exakt 44 Zeichen sein (Fernet format)")
        
        # Test: Kann Fernet damit initialisiert werden?
        Fernet(key_input.encode())
        
        _encryption_key = key_input
        print("✅ Key geladen")
        return _encryption_key
    
    except Exception as e:
        print(f"❌ Invalid key: {e}")
        raise

# Startup:
if __name__ == "__main__":
    if os.getenv("ENCRYPTION_KEY_SOURCE") == "user_input":
        encryption_key = get_encryption_key_from_user()
    else:
        encryption_key = get_encryption_key()
    
    app = create_app()
    app.run(...)
```

**Starte App mit User-Input:**
```bash
export ENCRYPTION_KEY_SOURCE=user_input
python3 -m src.00_main --serve --https --port 5003

# → Fragt nach Key im Terminal
```

---

## 🔄 SCHRITT 4: Secrets Rotation

### 4.1 Rotation Plan

```
┌─────────────────────────────────────────────────────────────┐
│ QUART. 1 (Jan-Mar 2026)                                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ 1. Neuen Secret in Vault/AWS generieren                     │
│ 2. App-Code: Support beiden Keys (old + new)                │
│ 3. Deployment: Mit neuem Key                                │
│ 4. Verifikation: App funktioniert mit neuem Key             │
│ 5. Cleanup: Old Key nach 30 Tagen entfernen                 │
│                                                              │
│ Timeline: 2-4 Wochen                                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Code: Dual-Key Support

```python
# src/helpers/encryption.py
"""Support für Encryption Key Rotation."""

import os
from cryptography.fernet import Fernet

class EncryptionKeyRotation:
    """Manage rotation von Encryption Keys."""
    
    def __init__(self):
        self.current_key = os.getenv("ENCRYPTION_CURRENT_KEY")
        self.previous_key = os.getenv("ENCRYPTION_PREVIOUS_KEY", None)
    
    def encrypt(self, plaintext: str) -> str:
        """Verschlüssele mit aktuellem Key."""
        cipher = Fernet(self.current_key)
        return cipher.encrypt(plaintext.encode()).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """
        Entschlüssele mit aktuellem oder vorherigem Key.
        (Ermöglicht Rotation ohne Downtime)
        """
        cipher_current = Fernet(self.current_key)
        cipher_previous = Fernet(self.previous_key) if self.previous_key else None
        
        try:
            # Versuche mit aktuellem Key
            return cipher_current.decrypt(ciphertext.encode()).decode()
        except Exception:
            # Fallback zu vorherigem Key
            if cipher_previous:
                try:
                    return cipher_previous.decrypt(ciphertext.encode()).decode()
                except Exception:
                    raise ValueError("Decryption failed with both keys!")
            else:
                raise

# Nutzer in Services:
encryptor = EncryptionKeyRotation()
encrypted_password = encryptor.encrypt(user_password)
decrypted_password = encryptor.decrypt(encrypted_password)
```

### 4.3 Rotation Script

```bash
#!/bin/bash
# scripts/rotate_encryption_key.sh

set -e

echo "🔄 ENCRYPTION KEY ROTATION"

# 1. Generiere neuen Key
NEW_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
OLD_KEY=$ENCRYPTION_CURRENT_KEY

echo "Old Key: ${OLD_KEY:0:20}..."
echo "New Key: ${NEW_KEY:0:20}..."

# 2. Update Vault
vault kv put secret/mail-helper/encryption \
  previous_key="$OLD_KEY" \
  current_key="$NEW_KEY" \
  rotation_date="$(date -I)"

# 3. Test: App startet mit neuen Keys
export ENCRYPTION_CURRENT_KEY="$NEW_KEY"
export ENCRYPTION_PREVIOUS_KEY="$OLD_KEY"
python3 -c "from src.helpers.encryption import EncryptionKeyRotation; EncryptionKeyRotation()" && \
  echo "✅ App startet mit neuen Keys"

# 4. Deploy mit neuen Keys
echo "4. Deploy App mit neuen Keys..."
# (deploy script hier)

# 5. Nach 30 Tagen: Old Key entfernen
echo "5. Nach 30 Tagen: Entferne OLD_KEY"
echo "   Reminder in 30 Tagen: vault kv put secret/mail-helper/encryption previous_key=null"

echo "✅ Rotation abgeschlossen!"
```

---

## 🛡️ SCHRITT 5: Security Checklist

### 5.1 Development

- [ ] ✅ `.env.local` existiert (NICHT `.env` committed)
- [ ] ✅ `.env.local` in `.gitignore`
- [ ] ✅ Keine Secrets in Code hardcoded
- [ ] ✅ `SECRET_KEY` generiert mit `os.urandom(32)`
- [ ] ✅ Passwörter min. 16 Zeichen komplexe Passwörter

### 5.2 Staging

- [ ] ✅ Secrets in Vault/AWS (NICHT in `.env`)
- [ ] ✅ PostgreSQL Password gerandom (32+ Zeichen)
- [ ] ✅ Redis Password gerandom (32+ Zeichen)
- [ ] ✅ App testet Secret-Loading
- [ ] ✅ Logs schreiben KEINE Secrets (auch nicht teilweise!)

### 5.3 Production

- [ ] ✅ Secrets in Vault/AWS/HSM (NICHT auf Disk)
- [ ] ✅ Nur Service-Account can access Secrets
- [ ] ✅ Audit-Log für Secret-Zugriffe aktiviert
- [ ] ✅ Secrets-Rotation Plan dokumentiert
- [ ] ✅ Monitoring: Alert wenn Secret-Zugriff fehlschlägt
- [ ] ✅ Backup-Plan: Was wenn Vault down ist? (Emergency Key?)

### 5.4 Code-Review

```python
# 🚫 FALSCH:
DATABASE_URL = "postgresql://user:password@localhost/db"
ENCRYPTION_KEY = "some_hardcoded_key_12345"

# ✅ RICHTIG:
DATABASE_URL = os.getenv("DATABASE_URL")
ENCRYPTION_KEY = get_encryption_key()  # Aus Vault/AWS

# 🚫 FALSCH:
logger.info(f"Connecting with password: {password}")

# ✅ RICHTIG:
logger.info(f"Connecting to {db_host} as {db_user}")  # Keine Password-Logs!
```

---

## 📚 SCHRITT 6: Dokumentation

### 6.1 DEPLOYMENT.md erstellen

```markdown
# Deployment Guide

## Secrets Management

### Local Development
1. Kopiere `.env.example` → `.env.local`
2. Trage Development-Werte ein
3. `source .env.local`

### Staging
1. Secrets in Vault speichern
2. `export VAULT_ENABLED=true`
3. `export VAULT_ADDR=http://vault.staging.example.com`
4. `python3 -m src.00_main --serve`

### Production
1. Secrets in AWS Secrets Manager
2. `export AWS_SECRETS=true`
3. EC2 IAM Role mit Secrets Manager Zugriff
4. `systemctl start mail-helper`

## Secrets Rotation

Jeden Monat:
```bash
bash scripts/rotate_encryption_key.sh
```
```

### 6.2 SECURITY.md erstellen

```markdown
# Security Policy

## Secrets Management

- ❌ Niemals Passwörter in Code
- ❌ Niemals `.env` in Produktion
- ✅ Vault/AWS Secrets für Produktion
- ✅ Monatliche Key-Rotation
- ✅ Audit-Logs für Secret-Zugriffe

## Incident Response

Wenn Secret gehackt:
1. Rotate sofort in Vault
2. Deploy neue Version
3. Audit-Logs prüfen
4. Benachrichtige User
```

---

## ✅ CHECKLISTE: Secrets Management

- [ ] `.env.example` erstellt
- [ ] `.env.local` in `.gitignore`
- [ ] Keine Secrets in Code hardcoded
- [ ] Vault/AWS Integration getestet (lokal mit mock)
- [ ] `src/helpers/secrets.py` geschrieben
- [ ] Encryption Key Rotation unterstützt
- [ ] Logging schreibt keine Secrets
- [ ] DEPLOYMENT.md dokumentiert
- [ ] SECURITY.md dokumentiert
- [ ] Secrets-Rotation Script vorhanden
- [ ] Production Security Review bestanden

---

## 🔗 Verwandte Docs

- [MULTI_USER_CELERY_LEITFADEN.md](MULTI_USER_CELERY_LEITFADEN.md) - Task-Implementierung
- [05_DEFINITION_OF_DONE.md](05_DEFINITION_OF_DONE.md) - DoD checklist

## 📚 Externe Ressourcen

- Vault Dokumentation: https://www.vaultproject.io/
- AWS Secrets Manager: https://aws.amazon.com/secrets-manager/
- Fernet (Cryptography): https://cryptography.io/en/latest/fernet/
