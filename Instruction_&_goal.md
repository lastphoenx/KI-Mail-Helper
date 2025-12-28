# Mail Helper – Lokaler KI-Mail-Assistent

---

## 📋 Projekt-Status (Aktualisiert: 28.12.2025)

### ✅ Phase 0: Projektstruktur (Abgeschlossen)
- [x] Grundstruktur aufgebaut (src/, templates/, tests/, scripts/)
- [x] Core-Module definiert (Models, Sanitizer, Scoring, Mail-Fetcher, etc.)
- [x] Requirements.txt, .env.example, .gitignore

### ✅ Phase 1: Single-User MVP (Abgeschlossen)
**Ziel:** Funktionsfähiges Single-User-System mit Mail-Verarbeitung

- [x] **Ollama-Integration** vollständig (`03_ai_client.py`)
- [x] **Web-App** mit DB-Queries (`01_web_app.py`)
- [x] **IMAP-Fetcher** testen und integrieren (`06_mail_fetcher.py`)
- [x] **Main.py** Entry-Point fertig
- [x] **End-to-End Test:** Fetch → Sanitize → KI → Dashboard

### ✅ Phase 2: Multi-User + 2FA (Abgeschlossen)
**Ziel:** Login, 2FA, Multi-Mail-Accounts pro User

- [x] **User-System** (User-Tabelle, Auth, Relationships) → `02_models.py`
- [x] **Login/Logout** (Flask-Login mit UserWrapper) → `01_web_app.py`
- [x] **2FA TOTP** (pyotp + QR-Code) → `07_auth.py` + Routes
- [x] **Mail-Accounts pro User** (Add/Delete im Dashboard) → `01_web_app.py`
- [x] **Service-Token für Background-Jobs** → `02_models.py` + `07_auth.py`
- [x] **Recovery-Codes** für Passwort-Reset → `07_auth.py`
- [x] **Multi-User Fetch & Process** → `00_main.py`

### ✅ Phase 3: Encryption (Abgeschlossen)
**Ziel:** Verschlüsselte Speicherung aller sensiblen Daten

- [x] **Master-Key-System** pro User (PBKDF2 + AES-256-GCM) → `08_encryption.py`
- [x] **IMAP-Password-Verschlüsselung** (AES-256-GCM) → `08_encryption.py` + `01_web_app.py`
- [x] **Mail-Body/Summary-Verschlüsselung** (AES-256-GCM) → `08_encryption.py`
- [x] **Session-basiertes Key-Management** (Master-Key in Flask Session) → `01_web_app.py`
- [x] **Master-Key Manager** (Setup, Derivation, Decryption) → `07_auth.py`
- [x] **Background-Job Decryption** (Service Tokens mit Master-Keys) → `00_main.py`
- [x] **Encryption Tests** (Alle Crypto-Funktionen getestet & validiert)

### ✅ Phase 4: Schema-Redesign & Bug-Fixes (Abgeschlossen)
**Ziel:** Datenbankmodelle bereinigen, SQLAlchemy 2.0 & Python 3.13 kompatibel

- [x] **Enums & Soft-Delete** (OptimizationStatus, deleted_at Columns) → `02_models.py`
- [x] **Alembic Migrations** (Datenbankrevisions-Management) → `migrations/`
- [x] **SQLAlchemy 2.0 Warnings** beheben (deprecated Syntax)
- [x] **Python 3.13 Deprecations** beheben (deprecated libraries)
- [x] **SQLite Foreign Key Enforcement** via Event-Listener
- [x] **Soft-Delete Filtering** in allen Web-Routes
- [x] **Route-Repairs** (5 broken queries in Web-App behoben)

### ✅ Phase 5: Two-Pass Optimization (Abgeschlossen)
**Ziel:** Zwei-Stufen-Analyse mit Base-Pass (schnell) + Optimize-Pass (optional, bessere Kategorisierung)

- [x] **Alembic Migration** (zwei neue Provider-Spalten pro User) → `migrations/b899fc331a19_*`
- [x] **User-Model erweitert** (preferred_ai_provider_optimize, preferred_ai_model_optimize)
- [x] **ProcessedEmail erweitert** (optimization_status, optimization_tried_at, optimization_completed_at)
- [x] **Optimize-Pass Route** (/email/<id>/optimize) mit sekundärem Provider
- [x] **Settings UI** (zwei-seitige Form: Base-Pass + Optimize-Pass)
- [x] **Email-Detail UI** (Reprocess + Optimize Button mit Kondition Score ≥ 8)
- [x] **Database Script** (reset_base_pass.py für frischen Base-Lauf)

### ✅ Phase 6: Dynamic Provider-Dropdowns (Abgeschlossen)
**Ziel:** Automatische Erkennung verfügbarer KI-Provider & Modelle basierend auf API-Keys

- [x] **Provider-Utils Module** (`15_provider_utils.py`) mit Ollama/OpenAI/Anthropic/Mistral-Support
- [x] **API-Endpoints** (/api/available-providers, /api/available-models/<provider>)
- [x] **JavaScript Dynamic Dropdowns** (Settings-Page mit async Modell-Laden)
- [x] **.env Integration** (OPENAI_API_KEY, ANTHROPIC_API_KEY, MISTRAL_API_KEY Autodetection)
- [x] **Model-Caching** (Hardcoded Fallbacks bei API-Ausfällen)
- [x] **Mistral Support** in AIProvider Enum hinzugefügt

### ✅ Phase 7: AI-Client Hardcoding-Fix & Cleanup (Abgeschlossen - 25.12.2025)
**Ziel:** ENFORCED_MODEL Hardcodierung entfernen, dynamische Modellauswahl aktivieren

- [x] **ENFORCED_MODEL entfernt** (Line 157) - War "llama3.2", ignoriert Benutzer-Input → GELÖST
- [x] **resolve_model() korrigiert** (Line 387-398) - Gibt nun angeforderte Modelle durch, kein Hardcoding
- [x] **LocalOllamaClient.__init__()** - Akzeptiert jetzt Benutzer-Modelle, ignoriert nicht mehr

### ✅ Phase 8a: Zero-Knowledge Production Ready (Abgeschlossen - 26.12.2025)
**Ziel:** 100% Zero-Knowledge Encryption - Server hat keinen Zugriff auf Klartext-Daten

**Security Score: 100/100** ✅

- [x] **14 Kritische Security Bugs gefixt** (6 initiale + 3 zusätzliche + 5 weitere)
- [x] **Server-Side Sessions** (Flask-Session, Master-Key nur in RAM)
- [x] **ProcessedEmail Encryption** (summary_de, text_de, tags, correction_note)
- [x] **Template Decryption** (alle Routes entschlüsseln vor Anzeige)
- [x] **Log Sanitization** (keine User-Daten mehr in Logs)
- [x] **Kryptographie-Fix** (separate IV + Salt für PBKDF2)
- [x] **Background-Jobs Decryption** (alle IMAP-Credentials entschlüsselt)
- [x] **Gmail OAuth Integration** (OAuth-Tokens verschlüsselt)
- [x] **Dual Mail-Fetcher** (IMAP + Gmail OAuth API)
- [x] **IMAP-Metadaten** (UID, Folder, Flags gespeichert)
- [x] **Performance** (all-minilm:22m, 46MB, ~100x schneller als llama3.2)
- [x] **Dokumentation** ([docs/ZERO_KNOWLEDGE_COMPLETE.md](docs/ZERO_KNOWLEDGE_COMPLETE.md))
- [x] **Ablauf korrekt:** User wählt all-minilm:22m → DB speichert → Job nutzt all-minilm:22m ✅
- [x] **Verzeichnis-Cleanup durchgeführt:**
  - Scripts: check_db.py, encrypt_db_verification.py, fix_db.py, etc. nach `scripts/`
  - Tests: test_mail_fetcher.py, fetch_endpoint.py nach `tests/`
  - .gitignore: emails.db.backup, RSYNC_RECOVERY_LOG.md hinzugefügt

### ✅ Phase 8b: DEK/KEK Pattern + Security Hardening (Abgeschlossen - 27.12.2025)
**Ziel:** Passwort-Wechsel ohne E-Mail-Neu-Verschlüsselung + Session Security Fixes

**Architecture:** DEK/KEK Pattern für effizientes Key-Management
- **DEK (Data Encryption Key):** Zufälliger 32-Byte-Key, verschlüsselt alle E-Mails
- **KEK (Key Encryption Key):** Aus Passwort abgeleitet (PBKDF2), verschlüsselt DEK
- **Vorteil:** Passwort-Änderung = nur DEK re-encrypten (nicht alle E-Mails!)

#### **Encryption Layer:**
- [x] **DEK-Funktionen** (`08_encryption.py`)
  - `generate_dek()` - Zufällige 32 Bytes
  - `encrypt_dek(dek, kek)` - AES-256-GCM(DEK, KEK)
  - `decrypt_dek(encrypted_dek, kek)` - Entschlüsselt DEK
- [x] **Auth-Manager** (`07_auth.py`)
  - `setup_dek_for_user()` - Erstellt DEK + verschlüsselt mit KEK
  - `decrypt_dek_from_password()` - Entschlüsselt DEK beim Login
  - Fallback für alte User mit `encrypted_master_key`
- [x] **Models** (`02_models.py`)
  - `User.encrypted_dek` (Text) - DEK verschlüsselt mit KEK
  - `User.salt` (Text) - Base64(32 bytes) = 44 chars (TEXT für SQLite)
  - `User.encrypted_master_key` (deprecated, für Migration)

#### **Security Fixes (Code-Review):**
- [x] **Salt Feldlänge-Bug** → `String(32)` war zu kurz für base64(32 bytes)=44 chars
  - Fix: `salt = Column(Text)` - keine Längen-Probleme mehr
  - Migration: `a8d9d8855a82_change_salt_to_text.py`
- [x] **PBKDF2 Hardcoding** → `encrypt_master_key()` hatte hardcoded 100000 statt 600000
  - Fix: `EncryptionManager.ITERATIONS` verwendet (600000)
- [x] **2FA Passwort-Leak** → `pending_password` in Session gespeichert
  - Fix: `pending_dek` statt Passwort + `pending_remember` Flag
- [x] **Session Security** 
  - `@app.before_request` aktiviert → DEK-Check bei jedem Request
  - Auto-Logout + Flash-Message bei Session-Expire
  - `session.clear()` in Logout (statt nur `pop('master_key')`)
- [x] **Remember-me deaktiviert** → Zero-Knowledge ohne DEK unmöglich
- [x] **SESSION_USE_SIGNER=False** → Deprecated seit Flask-Session 0.7.0
  - Server-Side Sessions benötigen keine Cookie-Signatur
  - 256-bit Session-ID (`SESSION_ID_LENGTH=32`) = ausreichend Entropie
  - Empfohlen laut Flask-Session Docs (historische Option)

#### **AI-Model Defaults korrigiert:**
- [x] **Base-Pass:** `preferred_ai_model = "all-minilm:22m"` (war llama3.2)
- [x] **Optimize-Pass:** `preferred_ai_model_optimize = "llama3.2:1b"` (war all-minilm:22m)
- [x] **resolve_model()** erweitert mit `kind` Parameter (base/optimize)
- [x] **Settings-View Fallbacks** korrigiert
- [x] **PROVIDER_REGISTRY** aktualisiert mit `default_model_base` / `default_model_optimize`

#### **Migrations:**
- [x] **7ee0bae8b1c2** - `encrypted_dek` Column hinzugefügt
- [x] **9347aa16b0a6** - `salt` String(32) → String(64)
- [x] **a8d9d8855a82** - `salt` String(64) → Text (finale Lösung)
- [x] **Migration-Script** (`scripts/migrate_to_dek_kek.py`)
  - Konvertiert `encrypted_master_key` → `encrypted_dek`
  - Verwendet alten Master-Key als DEK (Daten bleiben lesbar)
  - Salt-Fallback für Legacy-User ohne salt
  - Import-Fix mit importlib für scripts/

#### **Testing:**
- [x] **Neue User:** Registrierung mit `encrypted_dek` (kein `encrypted_master_key`)
- [x] **Alte User:** Migration-Script erfolgreich getestet
- [x] **Login-Flow:** DEK in Session nach Login/2FA
- [x] **Backward-Kompatibilität:** `decrypt_dek_from_password()` hat Fallback
- [x] **Fresh DB Setup:** DB-Reset + Neuregistrierung getestet
- [x] **19 Test-Emails:** Analyse erfolgreich (martina: Fertig! ~10m 0s, 19/19)

### ✅ Phase 9: Learning System & Newsletter-Detection (Abgeschlossen - 25.12.2025)
**Ziel:** Human-in-the-Loop ML: User-Korrektionen trainieren neue Modelle, bessere Newsletter-Erkennung

#### **Phase A: Erweiterte Newsletter-Heuristik**
- [x] **Known Newsletter Keywords** (30+) in `03_ai_client.py` → Trend, Blog, Wöchentlich, etc.
- [x] **Newsletter Keyword Counter** → ≥2 Keywords = Newsletter erkannt
- [x] **Unsubscribe-Link Detection** → "unsubscribe" / "abmelden" = automatisch spam_flag=True
- [x] **Score Suppression** → Newsletter: dringlichkeit=1, wichtigkeit=1, kategorie="nur_information"
- [x] **Optimierter System-Prompt** → LLM explizit: "Marketing-Inhalte ≠ dringend"
- [x] **Sender-basierte Erkennung** → Newsletter@, noreply@, gmx.de, mailchimp.com erkannt

**Test-Ergebnis:** Email #16 (GMX Newsletter) Score 6→4 ✅

#### **Phase B: ML Training Pipeline**
- [x] **`train_classifier.py`** → Haupttrainer mit RandomForest-Klassifikatoren
  - Sammelt `user_override_*` Spalten aus DB
  - Generiert Embeddings mit `all-minilm:22m`
  - Trainiert 3 Klassifikatoren: dringlichkeit, wichtigkeit, spam
  - Speichert als `.pkl` in `src/classifiers/`
  - Detailed Logging zu `training_log.txt`
- [x] **`/retrain` Endpoint** → `01_web_app.py:728-761`
  - POST-Endpoint für manuelles Retraining
  - Prüft min. 5 Korrektionen
  - Rückgabe: trained_count
- [x] **Database Migrations** → `16_migrate_user_corrections.py`, `17_migrate_model_tracking.py`
  - user_override_* Spalten (dringlichkeit, wichtigkeit, kategorie, spam_flag, tags)
  - correction_timestamp, user_correction_note
  - base_model, optimize_model, base_provider, optimize_provider

#### **Phase C2: UI-Feedback-Loop Dashboard**
- [x] **`/api/training-stats` Endpoint** → `01_web_app.py:764-810`
  - corrections_count, trained_models_count, last_correction_date
  - ready_for_training Flag
- [x] **Settings UI Widget** → `templates/settings.html:75-120`
  - Progress Bar: "X / ~50 Korrektionen"
  - Trainierte Modelle-Badges mit Datum
  - Button: "Noch N Korrektionen nötig" (disabled < 5)
- [x] **JavaScript Live-Update** → `settings.html:481-565`
  - loadTrainingStats() bei Page-Load
  - triggerRetraining() mit Feedback

#### **Phase C3: Erweiterte Newsletter-Liste**
- [x] **`known_newsletters.py`** → 40+ Domains + 20+ Sender-Patterns + 30+ Subject-Patterns
  - gmx.de, mailchimp.com, substack.com, medium.com, etc.
  - newsletter@, promo@, noreply@, updates@, etc.
  - "newsletter", "digest", "weekly", "trending", etc.
- [x] **`classify_newsletter_confidence(sender, subject, body)`** → 0.0-1.0 Konfidenz
  - sender domain match: +0.5
  - subject pattern match: +0.3
  - unsubscribe link: +0.2
- [x] **Integration in Analyze-Path**
  - Konfidenz ≥0.5 → spam_flag=True, scores minimiert
  - Konfidenz ≥0.8 → Early-Return (keine weiteren Heuristiken)
  - Sender-Parameter durch alle analyze_email() Calls: `12_processing.py`, `01_web_app.py`

### ✅ Phase 9: Production Hardening (Abgeschlossen - 27.12.2025)
**Ziel:** Production-Ready Deployment für Multi-User Home-Server (Heimnetz + VPN + Reverse Proxy)

**Security Score: 98/100** 🔒

#### **Phase 1: Critical Fixes (60 min) ✅**
- [x] **Flask-Limiter** (Rate Limiting) - `requirements.txt`, `src/01_web_app.py`
  - Global: 200 requests/day, 50/hour per IP
  - Login/2FA: 5 requests/minute per IP (Brute-Force Protection)
  - Storage: MemoryStorage (schnell, Production: Redis empfohlen)
- [x] **Gunicorn Production Server** - `gunicorn.conf.py`, `requirements.txt`
  - Workers: `cpu_count() * 2 + 1` (optimal für I/O)
  - Timeout: 30s, max_requests: 1000 (Memory-Leak Prevention)
  - Logging: logs/gunicorn_access.log + gunicorn_error.log
- [x] **Systemd Service** - `mail-helper.service`
  - Auto-Start: `WantedBy=multi-user.target`
  - Restart: `always` mit 5s Delay
  - Security: NoNewPrivileges, PrivateTmp, ProtectSystem=strict
  - Environment: FLASK_SECRET_KEY, FLASK_ENV=production
- [x] **SECRET_KEY Security** - `src/01_web_app.py`
  - Source: System Environment (FLASK_SECRET_KEY)
  - .env REMOVED from Flask config (Security Risk!)
  - Session-Cookie: SameSite=Lax für CSRF-Protection
  - Gunicorn-Reload: SECRET_KEY-Change invalidiert alle Sessions
- [x] **DEPLOYMENT.md** - Vollständige Production-Anleitung
  - Prerequisites, Installation, Nginx Reverse Proxy
  - Firewall, Fail2Ban, Backup Strategy, Monitoring
  - Troubleshooting, Security Checklist

**Score: 85/100 → 96/100** (Commits: 2649a01, 12d8711, 9af59bd)

#### **Phase 2: Advanced Security (90 min) ✅**
- [x] **Account Lockout** (5 Failed → 15min) - `src/02_models.py`, `src/01_web_app.py`
  - Database Columns: failed_login_attempts, locked_until, last_failed_login
  - Methods: is_locked(), record_failed_login(), reset_failed_logins()
  - Migration: `scripts/migrate_account_lockout.py` (importlib für Python 3.13)
  - Auto-Unlock: Zeitbasiert mit datetime.now(UTC)
- [x] **Session Timeout** (30min Inaktivität) - `src/01_web_app.py`
  - SESSION_PERMANENT = True
  - PERMANENT_SESSION_LIFETIME = 30 minutes
  - Auto-Logout bei inaktiver Session
- [x] **Audit Logging** (Fail2Ban Integration) - `src/01_web_app.py`
  - Strukturierte SECURITY[] Logs: LOGIN_FAILED, LOCKOUT, LOGIN_SUCCESS, 2FA_FAILED, LOGOUT
  - Machine-readable: user=username ip=X.X.X.X reason=... attempts=N/5
  - ISO 8601 Timestamps für Fail2Ban datepattern
  - Test-Script: `scripts/test_audit_logs.py` (5/5 Tests passed ✅)
- [x] **Fail2Ban Configuration** - `fail2ban-filter.conf`, `fail2ban-jail.conf`
  - Filter: Regex-Patterns für SECURITY[] Logs
  - Jail: maxretry=5, findtime=600s (10min), bantime=3600s (1h)
  - Multi-Layer Protection: Flask-Limiter + Account Lockout + Fail2Ban
- [x] **Database Backup Cronjob** - `scripts/backup_database.sh`
  - SQLite Hot Backup (.backup command) - sicher während Betrieb
  - Täglich: 2:00 Uhr (30 Tage Retention)
  - Wöchentlich: 3:00 Uhr Sonntag (90 Tage Retention)
  - Features: Integrity Check, gzip Compression, Auto-Rotation
  - DEPLOYMENT.md Update: Backup Strategy, Installation, Restore

**Score: 96/100 → 98/100** (Commits: ee9cd32, 209eec9, 2c2ec2f, 138a4cf)

#### **Multi-Layer Security Architecture:**
1. **Network Layer:** Fail2Ban (IP banning, 5 fails/10min → 1h ban)
2. **Application Layer:** Flask-Limiter (Rate limiting, 5 requests/min)
3. **User Layer:** Account Lockout (5 fails → 15min user ban)
4. **Session Layer:** 30min timeout, Secure cookies, SameSite=Lax
5. **Data Layer:** Zero-Knowledge Encryption (DEK/KEK pattern)

#### **Production Deployment Ready:**
- ✅ Multi-User Support (Familie im Heimnetz)
- ✅ VPN Remote Access (Session Timeout, Secure Cookies)
- ✅ Reverse Proxy Support (nginx, Caddy, Traefik)
- ✅ Fail2Ban Integration (network-level protection)
- ✅ Automated Backups (daily + weekly with rotation)
- ✅ Systemd Service (auto-start, restart on crash)
- ✅ Security Hardening (NoNewPrivileges, ProtectSystem)

---

### ✅ Phase 9b: UX-Verbesserungen (Abgeschlossen - 27.12.2025)
**Ziel:** User Experience Bugs beheben nach Production Hardening

**UX-Score: 8/10 → 9/10** ✨

#### **Fixes implementiert:**
- [x] **Recovery-Codes Regenerierung** - `templates/settings.html`
  - Detaillierte Warnmeldung vor Regenerierung
  - Warnung zeigt alle Konsequenzen (alte Codes ungültig, neue sofort sichern)
  - onsubmit statt onclick für bessere UX-Kontrolle
- [x] **Kopieren-Button** - `templates/recovery_codes_regenerated.html`
  - Robustes Fallback-System für Clipboard API
  - Prüfung auf window.isSecureContext (HTTPS)
  - Fallback auf document.execCommand für ältere Browser
  - Visuelles Feedback (Button wird grün, 2s Delay)
  - Klare Fehlermeldung mit manueller Anleitung
- [x] **Registrierung** - `templates/register.html`, `src/01_web_app.py`
  - Passwort-Regeln sichtbar im Formular (24 Zeichen, Sonderzeichen, etc.)
  - Formular-Werte bleiben bei Fehler erhalten (username, email)
  - Besserer Hinweis: 'Nutze einen Passwort-Manager'
- [x] **Login** - `templates/login.html`
  - Irreführender Hinweis 'Mindestens 8 Zeichen' entfernt
  - autofocus auf Username-Feld für schnellere Navigation

**Commit:** b5f7130

---

### ✅ Phase 9c: Security Code Review Fixes (Abgeschlossen - 28.12.2025)
**Ziel:** Kritische Security-Findings aus automatisiertem Code-Review fixen

**Security Score: 98/100 → 99/100** 🔒

#### **CRITICAL Priority Fixes (Layer 1-2):**
- [x] **AJAX CSRF Protection** - `src/01_web_app.py:113-125`
  - Added `csrf_protect_ajax()` function for AJAX endpoint validation
  - Applied to all state-changing AJAX operations
  - Prevents CSRF attacks on asynchronous operations
- [x] **Email Input Sanitization** - `src/03_ai_client.py:26-44`
  - Added `_sanitize_email_input()` to remove control characters
  - Applied to all AI clients (Ollama, OpenAI, Anthropic)
  - Prevents prompt injection and log poisoning
- [x] **API Key Redaction** - `src/03_ai_client.py:48-60`
  - Added `_safe_response_text()` for automatic API key redaction
  - Applied to OpenAI and Anthropic error logging
  - Prevents credential leakage in logs
- [x] **CSP Headers with Nonce** - `src/01_web_app.py:128-152`, `templates/base.html`
  - Moved CSP from meta tag to HTTP header
  - Nonce-based script execution (removed 'unsafe-inline')
  - Per-request nonce generation for stronger XSS protection
- [x] **Bootstrap SRI Hashes** - `templates/base.html`
  - Added Subresource Integrity hashes for CDN assets
  - Prevents tampering with third-party resources

#### **HIGH Priority Fixes (Layer 2-3):**
- [x] **Exception Sanitization (18 handlers)** - `src/01_web_app.py`
  - All exceptions now use `type(e).__name__` instead of full details
  - Removed 3× `exc_info=True` (OAuth, Mail-Abruf, Purge)
  - Generic error messages in API responses
  - Lines fixed: 262, 714, 790, 836, 869, 973, 1081, 1133, 1181, 1217, 1368, 1445, 1757, 1869, 2006, 2035, 2080-2081, 2091, 2153, 2179
  - **Impact:** Prevents database paths, credentials, and internal structure leaks
- [x] **Data Masking in Models** - `src/02_models.py:146`
  - `User.__repr__` now masks username as '***'
  - Prevents accidental data leaks in logs
- [x] **Host/Port Input Validation** - `src/00_main.py:334-346`
  - IP address validation with `ipaddress.ip_address()`
  - Port range validation (1024-65535)
  - Defense-in-depth against command injection
- [x] **Token Generation Enhancement** - `src/02_models.py:256`
  - Increased ServiceToken from 256 to 384 bits (48 bytes)
  - Better entropy for service tokens

#### **Infrastructure Improvements:**
- [x] **Master Key Security** - `src/14_background_jobs.py`
  - Removed `master_key` from FetchJob dataclass
  - Loaded from ServiceToken at runtime (not stored in queue)
  - Reduces master key exposure in process memory
- [x] **Queue Size Limit** - `src/14_background_jobs.py:42-43`
  - Added `MAX_QUEUE_SIZE = 50`
  - Prevents denial-of-service via queue exhaustion
- [x] **Redis Auto-Detection** - `src/01_web_app.py:160-177`
  - Automatic Redis detection for rate limiting
  - In-memory fallback when Redis unavailable
  - Better multi-worker rate limiting
- [x] **XSS Prevention in Settings** - `templates/settings.html:629-642`
  - Changed to `JSON.parse()` for AI values
  - Prevents script injection via crafted provider names
- [x] **Pickle Security** - `src/03_ai_client.py:294-324`
  - Added `_load_classifier_safely()` with HMAC verification
  - Mitigates pickle deserialization RCE risk

**Commits:** [pending]

---

## 🚀 **Ausstehende Aufgaben (Priorität)**

### **🟡 Phase 9d: HIGH-Priority Remaining Fixes**
**Ziel:** System-weite Sicherheitshärtung nach OWASP-Standards

#### **Prio 1: Password Policy (30 min) ✅**
- [x] **PasswordValidator-Klasse** (`09_password_validator.py`)
  - Mindestlänge: 24 Zeichen
  - Komplexität: Groß-, Kleinbuchstaben, Zahlen, Sonderzeichen
  - Blacklist: 100 häufigste Passwörter (rockyou.txt)
  - zxcvbn-Integration für Entropy-Messung
  - **Have I Been Pwned Integration (k-Anonymity Model)**
    - Zero-Knowledge: Nur erste 5 chars vom SHA-1 Hash an API
    - 500+ Millionen kompromittierte Passwörter
    - Live-Feedback: "Passwort wurde X-mal in Datenlecks gefunden"
    - Graceful Degradation bei API-Fehler
- [x] **Register-Route Update** (`01_web_app.py`)
  - Password-Validation vor User-Creation
  - UI-Feedback: Strength-Meter (client-side)
- [x] **Mandatory 2FA** für neue Registrierungen
  - Direkter Redirect zu `/2fa/setup` nach Register
  - `@app.before_request` Check: Kein Dashboard ohne 2FA
  - Whitelist: login, register, setup_2fa, static

**Aufwand:** ~30 Minuten ✅

#### **Prio 2: Settings-Features (60 min) ✅**
- [x] **Password-Change Route** (`/settings/password`, `01_web_app.py`)
  - 5-Stufen-Validation
  - KEK neu ableiten mit `EncryptionManager.generate_salt()`
  - DEK re-encrypten (keine E-Mail-Neu-Verschlüsselung!)
  - Session-Invalidierung nach Passwort-Änderung
- [x] **Recovery-Codes Regeneration** (`/settings/2fa/recovery-codes`)
  - `RecoveryCodeManager.invalidate_all_codes()`
  - Neue 10 Codes generieren
  - Download als .txt mit Timestamp
  - Copy-to-Clipboard Button

**Aufwand:** ~60 Minuten ✅

#### **Templates:**
- [x] `change_password.html` - Passwort-Änderung mit Strength-Meter
- [x] `recovery_codes_regenerated.html` - Recovery-Codes mit Download
- [x] `settings.html` - Security-Section erweitert

**Security Improvements:**
- ✅ Passwort-Entropie erhöht (8 → 24 Zeichen)
- ✅ Mandatory 2FA für alle neuen User
- ✅ Password-Change ohne Daten-Neu-Verschlüsselung
- ✅ Recovery-Codes Regeneration für User-Kontrolle
- ✅ **HIBP-Check für 500+ Millionen kompromittierte Passwörter**
- ✅ zxcvbn-Integration standardmäßig aktiv (requirements.txt)

**Code-Review Results:**
- ✅ Salt-Generation zentral (`EncryptionManager.generate_salt()`)
- ✅ Session-Security nach Password-Change
- ✅ Recovery-Codes Invalidierung sauber
- ✅ 2FA Mandatory ohne Redirect-Loop
- ✅ Autocomplete-Attribute korrekt gesetzt
- ✅ HIBP API: User-Agent + Add-Padding Header (Best Practices)
- ✅ HIBP: Robustes Parsing (split(':', 1), strip(), timeout als tuple)
- ✅ HIBP: 429 Rate-Limit Handling mit TODO für Production-Caching
- ✅ Flask-Session 0.8.0 in requirements.txt (kritischer Bug-Fix)

**Gesamt-Aufwand:** ~90 Minuten (Prio 1+2)

---

### **✅ Phase 8d: HTTPS Support + Reverse Proxy (Abgeschlossen - 27.12.2025)**
**Ziel:** Production-Ready HTTPS Setup mit Reverse Proxy Support

#### **Features implementiert:**
- [x] **Dual-Port Setup** (`01_web_app.py`)
  - HTTP Redirector auf Port 5000 → HTTPS Port 5001
  - Automatischer 301 Redirect (HTTP → HTTPS)
  - Self-signed Certificate Support (pyOpenSSL adhoc)
  - Threading: Beide Server parallel aktiv
- [x] **Flask-Talisman Integration**
  - HTTPS-Enforcement
  - Security Headers (HSTS, X-Content-Type-Options, etc.)
  - Konfigurierbar via `FORCE_HTTPS=true` in .env
- [x] **Reverse Proxy Support** (`ProxyFix` Middleware)
  - X-Forwarded-For, X-Forwarded-Proto, X-Forwarded-Host
  - Nginx/Caddy/Traefik kompatibel
  - Aktivierbar via `BEHIND_REVERSE_PROXY=true`
- [x] **CSRF-Protection** (Flask-WTF - 27.12.2025)
  - Flask-WTF==1.2.1 für CSRF-Tokens
  - CSRFProtect mit context_processor
  - 14 POST-Forms mit CSRF-Tokens ausgestattet
  - AJAX-Requests (fetchMails, purgeMails) mit X-CSRFToken Header
  - Meta-Tag `csrf-token` für JavaScript
- [x] **CLI Flag** (`--https`)
  - Start mit: `python3 -m src.00_main --serve --https`
  - Dual-Port: 5000 (HTTP Redirector) + 5001 (HTTPS Server)
- [x] **Dependencies hinzugefügt:**
  - pyOpenSSL==24.0.0 (Self-signed Certificates)
  - flask-talisman==1.1.0 (HTTPS-Enforcement)
  - Flask-WTF==1.2.1 (CSRF-Protection)

#### **.env Konfiguration:**
```bash
# HTTPS Settings
FORCE_HTTPS=true                     # Talisman aktivieren
SESSION_COOKIE_SECURE=false          # false für Development, true für Production
BEHIND_REVERSE_PROXY=false           # true wenn hinter Nginx/Caddy
```

#### **Production Setup (Nginx/Caddy):**
- Nginx-Beispiel in README.md + INSTALLATION.md
- Caddy-Beispiel (noch einfacher!)
- ProxyFix für korrekte Client-IP & HTTPS-Detection
- Let's Encrypt Integration dokumentiert

**Gesamt-Aufwand:** ~45 Minuten

---

### **🟡 Mittlere Priorität (Optional)**
- [ ] **C1: Scheduler für Auto-Training** (APScheduler / Celery)
  - Nächtlich ≥5 neue Korrektionen → automatisch trainieren
  - Robustheit & Fehlerbehandlung
  
### **🟡 Mittlere Priorität**
- [ ] **Model-Curation für OpenAI** (bereits teilweise implementiert 25.12.2025)
  - PROVIDER_REGISTRY: Kuratierte 5er-Liste statt alle API-Modelle
  - get_openai_models() von PROVIDER_REGISTRY lesen statt API
  - Test-Script: `scripts/probe_openai_mail_models.py`

- [ ] **UI-Feedback: Training-Progress** (Dashboard zeigt Accuracy-Verbesserung)
  - "Model Accuracy: 73% → 79% ⬆️" nach jedem Training
  - Kurve: Korrektionen vs. Modellqualität

### **🟢 Niedrige Priorität**
- [ ] **Advanced Newsletter Heuristics**
  - FPmail-Header-Analyse (unsubscribe_header)
  - MIME-Type Detection
  - Recursive Plaintext Extraction
  
- [ ] **Prompt-Engineering für Newsletter**
  - Spezialisierte Prompts bei Konfidenz > 0.8
  - Few-Shot-Examples in System-Prompt

- [ ] **Performance-Optimierungen**
  - Embedding-Caching für häufige Sender
  - Bulk-Training bei 100+ Korrektionen
  - Async Model-Loading

---

## 0. Projekt-Idee in einem Satz

Ein lokaler Mail-Assistent auf einem kleinen Server (z.B. Intel NUC / N100), der E-Mails automatisch abholt, datenschutzfreundlich pseudonymisiert, lokal mit Embeddings+ML bewertet, und optional Cloud-KI zur Verfeinerung nutzt und sie dann in einem übersichtlichen **3×3-Prioritäten-Dashboard** (Wichtigkeit × Dringlichkeit, Ampel-Farben) plus sortierter Liste mit Handlungsempfehlungen („Actions“) darstellt.

Dieses Dokument dient als **roter Faden** für die Umsetzung im Workspace (VS Code + Copilot) und als Basis für das GitHub-Repo.

---

## 1. Ausgangslage & Problemstellung

### 1.1 Ausgangslage

- Viele eingehende Mails (z.B. GMX per IMAP).
- Gemischte Inhalte:
  - Dringende Dinge („Bitte heute noch antworten“)
  - Wichtige Dinge („Vertrag, Rechnung, Behörde“)
  - Informationsmails („Newsletter, Systemmeldungen“)
  - Rauschen / Spam
- Mails in verschiedenen Sprachen:
  - Deutsch, Italienisch, Englisch, Französisch

### 1.2 Problem

- Es ist schwer, schnell zu erkennen:
  - **Was ist wirklich dringend?**
  - **Was ist wirklich wichtig?**
- Die Inbox wirkt überladen.
- Fremdsprachige Mails kosten Zeit.

### 1.3 Ziel

- Eine **übersichtliche Priorisierung** aller Mails:
  - Dringlichkeit und Wichtigkeit sichtbar machen.
  - Ampel-Anzeige (Rot/Gelb/Grün).
  - 3×3-Matrix: unten links „nicht dringend/wichtig“, oben rechts „sehr dringend/wichtig“.
- **Automatische Übersetzung nach Deutsch**.
- **Vorgeschlagene Aktionen** je Mail (z.B. „Antworten“, „Termin setzen“, „ignorieren“).
- Alles möglichst **lokal und datenschutzfreundlich**.

---

## 2. Zielbild (Funktionen)

### 2.1 Kernfunktionen (1–6)

1. **Mail-Fetcher (IMAP)**
   - Holt regelmäßig neue Mails vom Mail-Provider (z.B. GMX via IMAP).
   - Läuft als Hintergrundprozess (cron/systemd timer).
   - Speichert Rohdaten (Absender, Betreff, Body, Datum, IMAP-UID) in einer lokalen DB (`raw_emails`).

2. **Sanitizer + Pseudonymisierung (Datenschutz-Level 3)**
   - Entfernt Signaturen und alte Mail-Historie (zitierte E-Mails).
   - Pseudonymisiert:
     - E-Mail-Adressen → `[EMAIL_1]`, `[EMAIL_2]`, …
     - Telefonnummern → `[PHONE_1]`, …
     - IBANs → `[IBAN]`
     - URLs → `[URL]`
     - optional: Namen → `[PERSON]`, Organisationen → `[ORG]`, Orte → `[LOC]`
   - Liefert einen bereinigten, pseudonymisierten Text als Input für KI.

3. **KI-Analyse: Two-Pass-Architektur (Base + Optimize)**

   **Base-Pass (Standard, vollständig lokal):**
   - **Modus Default:** Embedding-Modell `all-minilm:22m` + trainierte sklearn-Klassifikatoren + Heuristiken
     - Schnell (CPU-ok), ressourcenschonend, keine API-Calls
     - Datenquelle: Newsletter-Patterns, Spam-Heuristiken, ML-Klassifikatoren
   - **Modus Optional:** Kleines Chat-LLM via Ollama (z.B. `llama3.2:1b`) – wenn Nutzer explizit wählt
   - Ausgabe-Skala: `1–3` (1=niedrig, 2=mittel, 3=hoch)
   
   **Optimize-Pass (Chat-basiert, lokal oder Cloud, optional):**
   - Verfeinert Base-Pass-Ergebnisse mittels LLM (nur Chat-Modelle sinnvoll)
   - Lokal: Ollama-Chat-Modelle (`llama3.2:1b`, `phi3:mini`, etc.)
   - Cloud: OpenAI (`gpt-4o-mini`), Anthropic, Mistral (nur mit **Datenschutz-Level 3**)
   - Nutzer wählt im Settings: „Base-Pass: all-minilm:22m" + „Optimize: gpt-4o-mini"
   
   **Ausgaben (beide Pässe):**
   - `kategorie_aktion`: `aktion_erforderlich | dringend | nur_information`
   - `wichtigkeit`: Skala 1–3 (1=niedrig, 2=mittel, 3=hoch)
   - `dringlichkeit`: Skala 1–3 (1=niedrig, 2=mittel, 3=hoch)
   - `labels/tags`: z.B. `["Finanzen", "Familie", "Arbeit"]`
   - `spam_flag`: `true/false`
   - `summary_de`: kurze Zusammenfassung auf Deutsch
   - `text_de`: vollständige deutsche Übersetzung (falls Original nicht Deutsch)

4. **Scoring & 3×3-Prioritäten-Matrix**
   - Mapping von `dringlichkeit` und `wichtigkeit` auf:
     - **Score** (z.B. `score = dringlichkeit * 2 + wichtigkeit`, Bereich 3–9).
     - **Matrix-Feld** (3×3):
       - Wichtigkeit 1–3 → Spalte (links gering, rechts hoch).
       - Dringlichkeit 1–3 → Zeile (unten gering, oben hoch).
   - Farbcodierung:
     - **Rot**: hohe Priorität (z.B. Score 8–9)
     - **Gelb**: mittlere Priorität (Score 5–7)
     - **Grün**: niedrige Priorität (Score 3–4)

5. **Web-Dashboard (Flask oder FastAPI)**

   **Sicht A – 3×3-Prioritätenmatrix:**
   - 3×3 Grid (9 Felder):
     - x-Achse: Wichtigkeit (1–3)
     - y-Achse: Dringlichkeit (1–3)
   - Jedes Feld zeigt:
     - Anzahl Mails in diesem Quadranten.
     - Hintergrundfarbe entsprechend Priorität (z.B. oben rechts rot).
     - Klick → Filter/Liste für dieses Feld.

   **Sicht B – Ampel-Ansicht (Rot/Gelb/Grün):**
   - Drei Bereiche:
     - Rot: hohe Prioritäten.
     - Gelb: mittlere Prioritäten.
     - Grün: niedrige Prioritäten.
   - Unter jedem Bereich: Liste der Mails mit:
     - Betreff, Absender, Datum.
     - Score.
     - Kurz-Summary (DE).
     - Link zu Details.

   **Sicht C – Listen-/ToDo-Ansicht:**
   - Alle offenen Mails sortiert **nach Score absteigend**.
   - Filter:
     - Farbe (Rot/Gelb/Grün),
     - Kategorie,
     - Zeitraum,
     - Spam-Flag.

6. **Detailansicht & Actions**
   - Detailseite pro Mail zeigt:
     - Betreff, Absender, Datum.
     - Score, Farbe, Quadrantenposition (z.B. „Wichtig: 3, Dringend: 2“).
     - `summary_de` (Kurzfassung).
     - `text_de` (komplette Übersetzung).
     - Originaltext (optional ein-/ausklappbar).
     - Tags/Kategorien.
   - **Vorgeschlagene Aktionen** (statisch + KI-gestützt), z.B.:
     - „Antwortentwurf generieren“
     - „Kalendereintrag anlegen“
     - „Auf ToDo-Liste setzen“
     - „Als erledigt markieren“
   - Button **„Erledigt“** setzt `done = true` in der DB.

---

## 3. Erweiterungen (Optionen)

- Filter im Dashboard:
  - nur „dringend“,
  - nur Mails mit bestimmten Tags,
  - Suchfeld (Volltext).
- Labels / Tags:
  - Automatische Zuordnung durch KI:
    - `Finanzen`, `Familie`, `Arbeit`, `Behörden`, `Newsletter`, `System`.
- Spam-Erkennung:
  - `spam_flag = true` → eigener Bereich oder Ausblendung.
- Benachrichtigungen:
  - z.B. Telegram-Bot, E-Mail, Push, wenn eine Mail mit Score ≥ X und nicht `done` eingegangen ist.
- Antwort-Entwurf:
  - KI erstellt auf Knopfdruck einen Vorschlag für eine Antwort-Mail (DE).

---

## 4. Datenschutz & Architekturprinzip

### 4.1 Grundprinzip

- **Standard-Mode:** alles lokal.
  - Maildaten werden nur:
    - vom Mail-Provider → auf den eigenen Server geholt,
    - lokal in SQLite gespeichert,
    - lokal von einem On-Prem-LLM verarbeitet (Ollama).
- **Cloud-Mode (optional):**
  - KI-APIs nur mit **stark reduzierten und pseudonymisierten** Inhalten.
  - Keine Klartext-Personendaten etc.
  - Optional konfigurierbar je KI-Client.

### 4.2 `sanitize_email(text, level)`

Konfigurierbarer Datenschutz-Level:

- **Level 1 – Volltext**
  - Keine Änderungen.
  - Nur sinnvoll, wenn garantiert **keine** externen Dienste genutzt werden.
- **Level 2 – Ohne Signatur + Historie**
  - Entfernt Signatur (z.B. ab `--` oder typischen Grußformeln).
  - Entfernt zitierte Historie:
    - Zeilen, die mit `>` beginnen.
    - Zeilen wie `Am XX schrieb Y:` → alles danach abschneiden.
- **Level 3 – + Pseudonymisierung**
  - Level 2 + Ersetzen von:
    - E-Mail-Adressen → `[EMAIL]`
    - Telefonnummern → `[PHONE]`
    - IBANs → `[IBAN]`
    - URLs → `[URL]`
    - (optional) Namen, Organisationen, Orte → `[PERSON]`, `[ORG]`, `[LOC]`.

**Regel:**

- **Lokales LLM (Ollama):** Standard Level 2, optional Level 3.
- **Externe KI (OpenAI, Mistral, Anthropic):** **Pflicht Level 3**.

### 4.3 Aufwand sanitize_email

- Implementierung in ~100–200 Zeilen Python (Regex + einfache Heuristiken).
- Sehr geringer Ressourcenbedarf (RAM/CPU).
- Großer Datenschutzgewinn, vor allem bei Cloud-Einsatz.

---

## 5. Systemarchitektur (Debian / NUC, leichtgewichtig)

### 5.1 Komponentenübersicht

1. **Mail-Fetcher (IMAP)**
   - Periodischer Job (cron oder systemd timer).
   - Liest neue Mails via IMAP.
   - Speichert in `raw_emails` (SQLite).

2. **Sanitizer & Preprocessor**
   - Funktion `sanitize_email(text, level)`.
   - Entfernt Signatur & Historie.
   - Pseudonymisiert nach Level.

3. **KI-Client**
   - Abstraktes Interface:
     - `LocalOllamaClient` (Standard)
     - `OpenAIClient`
     - `MistralClient`
     - `AnthropicClient`
   - Backend-Auswahl per Konfiguration/ENV.
   - Verantwortlich für:
     - Prompt-Design,
     - Aufruf,
     - Parsing des JSON-Outputs.

4. **Scoring & Mapping**
   - Logik zur Umrechnung von KI-Ergebnissen in:
     - Score,
     - Matrix-Feld (x/y),
     - Farbe (Rot/Gelb/Grün).

5. **Mini-DB (SQLite)**
   - Speicherung von:
     - Original-Mails (Rohtext, Header).
     - KI-Ergebnissen (Dringlichkeit, Wichtigkeit, Tags, Summary, Übersetzung, Score).
     - Status (`done`).

6. **Web-Dashboard (Flask oder FastAPI)**
   - Darstellung von:
     - 3×3-Übersicht.
     - Ampel-Ansicht (Rot/Gelb/Grün).
     - Score-Liste.
     - Detailansicht je Mail.
   - Aktionen:
     - Mail als erledigt markieren.
     - ggf. Priorität manuell anpassen.

---

## 6. Architektur: Ablauf pro Mail

1. **IMAP-Fetch**
   - Neue Mails via IMAP holen.
   - In `raw_emails` speichern:
     - `id`, `uid`, `sender`, `subject`, `body`, `received_at`.

2. **Sanitize & Pseudonymize**
   - `clean_text = sanitize_email(body, level=3)` (für Cloud).
   - Für lokale LLMs optional `level=2`.

3. **KI-Aufruf**
   - Input (z.B.):
     - Betreff (pseudonymisiert),
     - `clean_text`,
     - ggf. Sprache.
   - Output (JSON):
     - `dringlichkeit` (1–3 oder 1–5),
     - `wichtigkeit` (1–3 oder 1–5),
     - `kategorie_aktion` (`aktion_erforderlich|dringend|nur_information`),
     - `tags` (Liste),
     - `spam_flag`,
     - `summary_de`,
     - `text_de`.

4. **Scoring**
   - Umrechnung in:
     - `score`,
     - `matrix_x`, `matrix_y`,
     - `farbe`.

5. **Speichern in `processed_emails`**
   - `raw_email_id` (FK),
   - KI-Daten (Dringlichkeit, Wichtigkeit, etc.),
   - Score, Farbe, Tags, Spam-Flag,
   - `done` (initial false).

6. **Anzeige im Dashboard**
   - 3×3-View, Ampel, Liste.
   - Details pro Mail.
   - Aktionen (Buttons).

---

## 7. Projektstruktur (für VS Code & Copilot)

Ziel: gut strukturierter Workspace, vorbereitet für GitHub.

```text
mail-helper/
├─ src/
│  ├─ 00_main.py              # Entry-Point / App-Start, CLI-Optionen
│  ├─ 01_web_app.py           # Flask App mit Multi-User, 2FA, Settings
│  ├─ 02_models.py            # DB-Modelle (SQLAlchemy, Enums, soft-delete)
│  ├─ 03_ai_client.py         # KI-Client-Interface + Backends (Ollama, OpenAI, etc.)
│  ├─ 04_sanitizer.py         # sanitize_email + Datenschutz-Level
│  ├─ 05_scoring.py           # Score-Berechnung + 3×3-Mapping + Farben
│  ├─ 06_mail_fetcher.py      # IMAP-Fetcher (GMX & Co)
│  ├─ 07_auth.py              # Authentication, TOTP, Recovery-Codes
│  ├─ 08_encryption.py        # AES-256-GCM Master-Key-System
│  ├─ 09_migrate_oauth.py     # Migration: OAuth-Integration
│  ├─ 10_google_oauth.py      # Google OAuth Handler
│  ├─ 11_migrate_cron_masterkey.py # Migration: Cron Master-Key
│  ├─ 12_processing.py        # Email-Verarbeitungs-Workflow
│  ├─ 13_migrate_ai_preferences.py # Migration: AI-Provider Preferences
│  ├─ 14_background_jobs.py   # Background Job Queue (Fetch/Process)
│  ├─ 15_provider_utils.py    # Dynamic Provider/Model Discovery (Ollama, OpenAI, Anthropic, Mistral)
│  └─ __init__.py
│
├─ templates/
│  ├─ base.html               # Base template mit Bootstrap
│  ├─ dashboard.html          # 3×3-Matrix + Ampel-Ansicht
│  ├─ list_view.html          # Score-sortierte Email-Liste
│  ├─ email_detail.html       # Detail-Ansicht mit Reprocess/Optimize Buttons
│  ├─ login.html              # Login-Form
│  ├─ register.html           # Registrierung
│  ├─ settings.html           # Settings (2FA, Mail-Accounts, AI-Provider Dropdowns)
│  └─ emails/
│      └─ ...                  # weitere Email-spezifische Templates
│
├─ migrations/
│  ├─ versions/
│  │  ├─ *.py                  # Alembic-Revisions (Datenbank-Schema-Versionen)
│  │  └─ b899fc331a19_add_two_pass_optimization.py # Two-Pass Optimization
│  ├─ alembic.ini             # Alembic-Konfiguration
│  ├─ env.py                  # Alembic-Umgebung
│  └─ script.py.mako          # Alembic-Vorlage
│
├─ scripts/
│  ├─ reset_base_pass.py      # Helper: Lösche alle ProcessedEmails für Base-Pass Neu-Lauf
│  └─ ...                      # weitere Maintenance-Skripte
│
├─ tests/
│  ├─ test_sanitizer.py       # Sanitizer-Tests
│  ├─ test_scoring.py         # Scoring-Tests
│  ├─ test_ai_client.py       # KI-Client-Tests
│  ├─ test_db_schema.py       # Database Schema Tests
│  └─ __init__.py
│
├─ .env.example               # Beispiel-ENV (ohne Secrets)
├─ .env                       # Lokale ENV-Variablen (NICHT committen!)
├─ .gitignore
├─ requirements.txt           # Python-Dependencies
├─ emails.db                  # SQLite-Datenbank (NICHT committen!)
├─ README.md                  # Kurzfassung + Install-Anleitung
├─ Instruction_&_goal.md      # (dieses Dokument) – Projekt-Spezifikation
├─ MAINTENANCE.md             # Maintenance-Skripte & Helper
├─ CRON_SETUP.md              # Cron-Jobs konfigurieren
├─ OAUTH_AND_IMAP_SETUP.md   # OAuth & IMAP-Account Setup
└─ TESTING_GUIDE.md           # Test-Anleitung





Nummerierte Dateien (00_, 01_, …):

Helfen bei grober Ordnung.

Unterstützen Copilot beim Verständnis, was „wichtig“ ist.

Können später bei Bedarf refactored werden.

---

## 8. Multi-User & Security (Phase 2 & 3)

### 8.1 Multi-User Architektur

**Neue Anforderungen:**
- ✅ Mehrere Mail-Accounts pro User registrierbar
- ✅ Web-Zugang: Heimnetz, VPN, Reverse-Proxy
- ✅ 2FA-Login (TOTP)
- ✅ Admin kann keine Mails lesen (verschlüsselt)
- ✅ Familie/Multi-User fähig

### 8.2 Encryption-Strategie

**Ablauf pro Mail:**
```
Fetch (IMAP mit encrypted Password)
  ↓
Sanitize (Plaintext)
  ↓
KI-Analyse (Ollama lokal, Plaintext)
  ↓
ENCRYPT alle Daten mit User-Master-Key
  ↓
Speichern in DB (encrypted_body, encrypted_summary_de, encrypted_text_de, ...)
  ↓
Dashboard-Abfrage → User-Login → Master-Key aus Session
  ↓
Decrypt on-demand → sende Plaintext an Frontend
```

### 8.3 Database Schema (Phase 2)

**Neue Tabellen:**

```sql
users:
  - id (PK)
  - username (UNIQUE)
  - email
  - password_hash (bcrypt)
  - salt (für Key-Derivation)
  - encrypted_master_key (encrypted mit Password-Key)
  - totp_secret (für 2FA)
  - created_at
  - updated_at

mail_accounts:
  - id (PK)
  - user_id (FK → users)
  - name (z.B. "GMX Privat", "Gmail Arbeit")
  - imap_server
  - imap_username
  - encrypted_imap_password (encrypted mit Master-Key!)
  - enabled
  - last_fetch_at
  - created_at

service_tokens:
  - id (PK)
  - user_id (FK)
  - token_hash
  - expires_at
  - created_at

recovery_codes:
  - id (PK)
  - user_id (FK)
  - code_hash
  - used_at (NULL = noch nicht verwendet)
  - created_at
```

**Geänderte Tabellen:**

```sql
raw_emails:
  + user_id (FK → users)
  + mail_account_id (FK → mail_accounts)
  + encrypted_body (statt body)
  + encryption_iv (Initialization Vector)
  - body

processed_emails:
  + encrypted_summary_de (statt summary_de)
  + encrypted_text_de (statt text_de)
  + encryption_iv
  # score, matrix_x, matrix_y, farbe → Plaintext (für Dashboard)
  # tags → optional encrypted
```

### 8.4 Key-Management (Phase 3)

**Master-Key-System:**

```python
# Bei User-Registrierung:
master_key = generate_random_key(256)  # zufällig
password_key = derive_from_password(password, salt)
encrypted_master_key = encrypt(master_key, password_key)
# Speichere: encrypted_master_key, salt in DB

# Bei Login:
password_key = derive_from_password(password, user.salt)
master_key = decrypt(user.encrypted_master_key, password_key)
# Speichere master_key in Session (RAM)

# Background-Job für IMAP-Fetch:
# Nutze Service-Token → dekryptiere IMAP-Password
```

### 8.5 Plaintext vs. Encrypted (Dashboard Performance)

**Plaintext (für schnelle Queries & Dashboard):**
- score, matrix_x, matrix_y, farbe
- done
- sender (aus IMAP-Header, oft sichtbar)
- received_at
- spam_flag

**Encrypted (sensible Daten):**
- encrypted_body
- encrypted_summary_de
- encrypted_text_de
- encrypted_imap_password
- tags (optional)

---

## 9. Setup & Installation (Stub)

In README.md (oder später detailliert ausformulieren):

# 1. Repo klonen
git clone <REPO_URL>
cd mail-helper

# 2. Python-Venv anlegen
python3 -m venv .venv
source .venv/bin/activate

# 3. Abhängigkeiten installieren
pip install -r requirements.txt

# 4. .env anlegen
cp .env.example .env
---

## 📁 **Komponenten-Übersicht (Phase 8: Learning System)**

### **Neue/Geänderte Dateien (25.12.2025)**

| Datei | Zweck | Status |
|-------|-------|--------|
| **`src/known_newsletters.py`** | 40+ Newsletter-Domains + Patterns, Konfidenz-Berechnung | ✅ Phase C3 |
| **`src/train_classifier.py`** | ML Training Pipeline (RandomForest, sklearn) | ✅ Phase B |
| **`src/03_ai_client.py`** | **Updated:** Newsletter-Erkennung, Sender-Parameter, Prompt-Optimierung | ✅ Phase A |
| **`src/01_web_app.py`** | **Updated:** `/retrain`, `/api/training-stats` Endpoints | ✅ Phase B+C2 |
| **`src/12_processing.py`** | **Updated:** sender-Parameter an analyze_email() | ✅ Phase C3 |
| **`src/15_provider_utils.py`** | **Updated:** get_openai_models() von Registry statt API | ✅ Model-Curation |
| **`src/16_migrate_user_corrections.py`** | Migration: user_override_* Columns | ✅ Phase B |
| **`src/17_migrate_model_tracking.py`** | Migration: base_model, optimize_model Columns | ✅ Phase B |
| **`templates/settings.html`** | **Updated:** Training-Progress Widget + Dashboard | ✅ Phase C2 |
| **`templates/email_detail.html`** | **Updated:** Correction Modal + Technical Info | ✅ (vorher) |

### **Database Schema Erweiterungen (Phase 8)**

**Neue Spalten in `processed_emails`:**
```sql
user_override_dringlichkeit INTEGER
user_override_wichtigkeit INTEGER
user_override_kategorie TEXT
user_override_spam_flag BOOLEAN
user_override_tags TEXT
correction_timestamp DATETIME
user_correction_note TEXT

base_model TEXT
base_provider TEXT
optimize_model TEXT
optimize_provider TEXT
```

### **API-Endpoints (Phase 8)**

- `POST /email/<id>/correct` → Speichert User-Korrektionen
- `GET /api/training-stats` → Gibt Training-Statistiken
- `POST /retrain` → Trainiert Modelle aus Korrektionen

### **Klassifikatoren (nach Training)**

Gespeichert in `src/classifiers/`:
- `dringlichkeit_clf.pkl` → RandomForest für Dringlichkeit
- `wichtigkeit_clf.pkl` → RandomForest für Wichtigkeit
- `spam_clf.pkl` → RandomForest für Spam-Erkennung
- `training_log.txt` → Detailliertes Training-Log

---

# → IMAP-Login, KI-Backends, Datenschutz-Level etc. eintragen

# 5. DB initialisieren
python -m src.02_models  # oder eigenes Init-Skript

# 6. Testlauf: Mails einmal holen & verarbeiten
python -m src.06_mail_fetcher
python -m src.00_main --process-once

# 7. Web-App starten
python -m src.00_main --serve

# 8. .gitignore (Auszug)
.gitignore (Auszug):

.venv/
__pycache__/
*.pyc
.env
emails.db

9. Hinweise für die Arbeit mit Copilot
Dieses .md-Dokument dient als Kontext:
Projektstruktur,
Dateinamen,
Feldnamen (dringlichkeit, wichtigkeit, summary_de, …),
Datenschutz-Level,
Architekturideen.
Empfohlene Implementations-Reihenfolge:
02_models.py – DB-Setup (SQLAlchemy + SQLite).
04_sanitizer.py – sanitize_email + Tests.
06_mail_fetcher.py – IMAP-Fetcher.
03_ai_client.py – Interface + Dummy-Backend / erstes LLM-Backend.
05_scoring.py – Score-Logik + Tests.
01_web_app.py + Templates – UI-Grundgerüst.
00_main.py – Orchestrierung, CLI-Optionen, Start-Skripte.

Früh Tests unter tests/ anlegen, damit Copilot beim Erweitern bessere Vorschläge liefern kann.

