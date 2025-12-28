# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Security Fixes - Phase 9c (2025-12-28)

#### MEDIUM Priority Security Improvements

**Timing-Attack Protection**
- Added constant-time user enumeration protection in login flow
- Dummy bcrypt check for non-existent users normalizes response timing
- **Impact**: Prevents attacker from determining valid usernames via timing analysis
- **Files**: `src/01_web_app.py` (lines 339-351)

**Input Validation Setters**
- Added validation setters for User model fields
- `set_username()`: 3-80 characters, `set_email()`: 1-255 characters, `set_password()`: 8-255 characters
- Integrated into registration flow to enforce validation
- **Impact**: Prevents memory exhaustion attacks and enforces data quality
- **Files**: `src/02_models.py` (lines 115-135), `src/01_web_app.py` (lines 465-467)

**Debug-Log Masking**
- Masked user IDs in auth.py logger statements (6 locations)
- Changed exception logging to use `type(e).__name__` instead of full details (2 additional locations)
- **Impact**: Prevents user ID and exception detail leaks in logs/backups
- **Files**: `src/07_auth.py` (lines 100, 131, 164, 186, 215, 247, 287, 294, 298, 317)

**Security Headers for Error Responses**
- Security headers now applied to ALL responses (including 4xx/5xx errors)
- Moved X-Content-Type-Options, X-Frame-Options, Referrer-Policy outside status check
- CSP only for successful responses (requires nonce from request context)
- **Impact**: Prevents XSS via error messages, defense-in-depth for all response types
- **Files**: `src/01_web_app.py` (lines 144-147)

**JS Polling Race Condition**
- Added `pollingActive` flag to prevent multiple concurrent polling loops
- Race condition protection for rapid button clicks
- Reset flag on all exit paths (done, error, timeout, fetch-error)
- **Impact**: Prevents UI inconsistencies, multiple API calls, and rate limit triggers
- **Files**: `templates/settings.html` (lines 285-291, 337, 355, 373, 402)

**SQLite Deadlock Multi-Worker Fix**
- Enabled WAL Mode (Write-Ahead Logging) for concurrent read access
- Added busy_timeout=5000ms for automatic retry on lock conflicts
- WAL autocheckpoint every 1000 pages to prevent unbounded .wal file growth
- Updated backup script to use WAL-aware `.backup` command
- **Impact**: Eliminates SQLITE_BUSY errors in multi-worker setup, readers don't block during writes
- **Files**: `src/02_models.py` (lines 500-527), `scripts/backup_database.sh` (line 56)
- **Testing**: `scripts/verify_wal_mode.py`, `scripts/test_concurrent_access.py`

---

### Security Fixes - Phase 9b (2025-12-28)

#### HIGH Priority Security Improvements

**Exception Sanitization (18 handlers fixed)**
- Changed all exception handlers to use `type(e).__name__` instead of exposing full exception details
- Removed 3 instances of `exc_info=True` that leaked stack traces (OAuth, Mail-Abruf, Purge)
- Generic error messages in API responses instead of `str(e)` to prevent information disclosure
- **Impact**: Prevents database paths, credentials, and internal structure from leaking in logs
- **Files**: `src/01_web_app.py` (lines 262, 714, 790, 836, 869, 973, 1081, 1133, 1181, 1217, 1368, 1445, 1757, 1869, 2006, 2035, 2080-2081, 2091, 2153, 2179)

**Data Masking in Models**
- Added masking for sensitive data in `__repr__` methods
- `User.__repr__` now shows `username='***'` instead of actual username
- **Impact**: Prevents accidental data leaks when model objects are logged
- **Files**: `src/02_models.py` (line 146)

**Host/Port Input Validation**
- Added IP address validation using `ipaddress.ip_address()` in CLI arguments
- Port range validation (1024-65535) for non-root deployment safety
- **Impact**: Defense-in-depth against command injection and misconfiguration
- **Files**: `src/00_main.py` (lines 334-346)

**Token Generation Enhancement**
- Increased `ServiceToken.generate_token()` from 256 to 384 bits (32 → 48 bytes)
- Better entropy for service tokens used in background jobs
- **Impact**: Stronger protection against brute-force attacks on service tokens
- **Files**: `src/02_models.py` (line 256)

#### CRITICAL Priority Security Improvements

**AJAX CSRF Protection**
- Added `csrf_protect_ajax()` function for validating CSRF tokens in AJAX requests
- Applied to all state-changing AJAX endpoints
- **Impact**: Prevents CSRF attacks on asynchronous operations
- **Files**: `src/01_web_app.py` (lines 113-125)

**Email Input Sanitization**
- Added `_sanitize_email_input()` function to remove control characters from email content
- Applied to all AI clients (Ollama, OpenAI, Anthropic) before analysis
- Prevents prompt injection and log poisoning attacks
- **Impact**: Protects AI processing pipeline from malicious email content
- **Files**: `src/03_ai_client.py` (lines 26-44, applied at 453, 510, 554)

**API Key Redaction**
- Added `_safe_response_text()` function to redact API keys from error messages
- Applied to OpenAI and Anthropic error logging
- **Impact**: Prevents API key leakage in logs when AI providers return errors
- **Files**: `src/03_ai_client.py` (lines 48-60, applied at 507, 551)

**CSP Headers with Nonce**
- Moved CSP from meta tag to HTTP header with nonce-based script execution
- Added `set_security_headers()` function with per-request nonce generation
- Removed `'unsafe-inline'` from CSP policy
- **Impact**: Stronger XSS protection without allowing inline scripts
- **Files**: `src/01_web_app.py` (lines 128-152), `templates/base.html` (removed meta tag)

**Subresource Integrity (SRI)**
- Added SRI hashes for Bootstrap CSS and JavaScript from CDN
- **Impact**: Prevents tampering with third-party CDN resources
- **Files**: `templates/base.html`

**XSS Prevention in Settings**
- Changed AI provider/model values to use `JSON.parse()` instead of direct template interpolation
- **Impact**: Prevents script injection via crafted AI provider/model names
- **Files**: `templates/settings.html` (lines 629-642)

#### Infrastructure Improvements

**Master Key Security**
- Removed `master_key` parameter from `FetchJob` dataclass
- Master key now loaded from `ServiceToken` at runtime instead of being stored in queue
- **Impact**: Reduces master key exposure in process memory
- **Files**: `src/14_background_jobs.py` (lines 28-35, 74-89, 153-162), `src/01_web_app.py`

**Queue Size Limit**
- Added `MAX_QUEUE_SIZE = 50` to prevent unbounded queue growth
- **Impact**: Prevents denial-of-service via queue exhaustion
- **Files**: `src/14_background_jobs.py` (lines 42-43, 48)

**Redis Auto-Detection**
- Added automatic Redis detection for rate limiting with in-memory fallback
- **Impact**: Better rate limiting in multi-worker deployments when Redis available
- **Files**: `src/01_web_app.py` (lines 160-177)

**Pickle Security Enhancement**
- Added `_load_classifier_safely()` with optional HMAC verification for pickle files
- **Impact**: Mitigates pickle deserialization RCE risk (defense-in-depth)
- **Files**: `src/03_ai_client.py` (lines 294-324)

---

## [Phase 8b] - 2025-12-27

### Added - DEK/KEK Pattern
- Implemented Data Encryption Key (DEK) / Key Encryption Key (KEK) pattern
- Password changes now only re-encrypt DEK instead of all emails
- Added `generate_dek()`, `encrypt_dek()`, `decrypt_dek()` functions

### Fixed - Security Issues
- Fixed salt field length (String(32) → Text) for base64 encoding
- Fixed PBKDF2 hardcoding in `encrypt_master_key()` (100000 → 600000)
- Fixed 2FA password leak (stored `pending_dek` instead of password)
- Enabled `@app.before_request` DEK validation
- Removed remember-me functionality (incompatible with Zero-Knowledge)
- Removed deprecated `SESSION_USE_SIGNER` flag

### Changed - AI Model Defaults
- Base-Pass default: `all-minilm:22m` (was llama3.2)
- Optimize-Pass default: `llama3.2:1b` (was all-minilm:22m)

---

## [Phase 8a] - 2025-12-26

### Added - Zero-Knowledge Encryption
- Full end-to-end encryption for all sensitive data
- AES-256-GCM encryption for emails, credentials, OAuth tokens
- Server-side sessions for master key storage (RAM only)
- Gmail OAuth integration with encrypted token storage
- IMAP metadata tracking (UID, Folder, Flags)

### Fixed
- 14 critical security bugs from code review
- Log sanitization (no user data in logs)
- Background job decryption
- Separate IV + Salt for PBKDF2

---

## [Phase 7] - 2025-12-25

### Fixed - AI Client
- Removed `ENFORCED_MODEL` hardcoding
- Fixed `resolve_model()` to respect user model selection
- Dynamic model selection now works correctly

---

## [Phase 6] - 2025-12-25

### Added - Dynamic Provider Detection
- Automatic detection of available AI providers based on API keys
- Dynamic model dropdowns in settings UI
- `/api/available-providers` and `/api/available-models/<provider>` endpoints
- Support for Mistral AI provider

---

## [Phase 5] - 2025-12-25

### Added - Two-Pass Optimization
- Base-Pass: Fast initial analysis
- Optimize-Pass: Optional detailed analysis for high-priority emails
- Separate AI provider/model settings for each pass
- `optimization_status` tracking in `ProcessedEmail`

---

## [Phase 4] - 2025-12-24

### Fixed - Database Schema
- SQLAlchemy 2.0 compatibility
- Python 3.13 deprecation warnings
- Soft-delete filtering in all routes
- SQLite foreign key enforcement

---

## [Phase 3] - 2025-12-23

### Added - Encryption
- Master key system (PBKDF2 + AES-256-GCM)
- IMAP password encryption
- Email body/summary encryption
- Session-based key management

---

## [Phase 2] - 2025-12-22

### Added - Multi-User Support
- User authentication system
- 2FA (TOTP) with QR code setup
- Recovery codes
- Multi mail-accounts per user
- Service tokens for background jobs

---

## [Phase 1] - 2025-12-21

### Added - MVP
- Ollama integration for email analysis
- Web dashboard with Flask
- IMAP mail fetcher
- Basic email processing pipeline

---

## [Phase 0] - 2025-12-20

### Added - Project Setup
- Initial project structure
- Core modules defined
- Requirements and configuration files
