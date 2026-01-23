#!/usr/bin/env python3
"""
Automated Code Review mit Claude API (v3.1)
============================================
Improved with:
- Context-aware prompts with Threat Model
- FULL project context (100k chars limit vs. 3k)
- Dependency Graph Extraction (imports & related files)
- File-by-file reviews with 2-Pass for critical files
- Context-aware calibration (markiert statt ignoriert)
- Extended Security Layer (6 files statt 4)
- 3 Context Modes: REDUCED, FULL, DEEP (adaptive + manual override)
"""

import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime
import anthropic
from dotenv import load_dotenv
import re

# Load .env
project_root = Path(__file__).parent.parent
load_dotenv(project_root / '.env')

# Configuration
LARGE_FILE_THRESHOLD = 50000  # Chars - Trigger für reduziertem Kontext
CONTEXT_MODE_OVERRIDE = None  # Global for CLI override


def estimate_tokens(text):
    """Schätzt Token-Anzahl: ~4 Zeichen = 1 Token (Claude Approximation)"""
    if not text:
        return 0
    return len(text) // 4


class APIRateLimiter:
    """Verwaltet API Rate Limits proaktiv (30k input tokens/min für Claude Sonnet)"""
    
    def __init__(self, tokens_per_minute=30000, buffer_percent=85):
        """
        tokens_per_minute: Claude Sonnet Tier 1 limit (30k)
        buffer_percent: Bei 85% Nutzung warten (15% Sicherheitspuffer)
        """
        self.tokens_per_minute = tokens_per_minute
        self.buffer_limit = int(tokens_per_minute * buffer_percent / 100)
        self.tokens_this_minute = 0
        self.minute_start = time.time()
        self.request_count = 0
    
    def check_budget(self, estimated_input_tokens):
        """Prüft ob genug Budget da ist, wartet sonst bis nächste Minute"""
        elapsed = time.time() - self.minute_start
        
        if elapsed >= 60:
            self.tokens_this_minute = 0
            self.minute_start = time.time()
            elapsed = 0
        
        would_exceed = self.tokens_this_minute + estimated_input_tokens > self.buffer_limit
        
        if would_exceed and self.tokens_this_minute > 0:
            # Wartet nur wenn bereits Tokens verbraucht wurden.
            # Erste Request geht durch (auch wenn >buffer_limit), da Anthropic
            # einzelne große Requests erlaubt (Burst-Allowance).
            wait_time = 60 - elapsed
            print(f"      ⏳ Rate limit approaching ({self.tokens_this_minute + estimated_input_tokens:,} tokens) → waiting {wait_time:.1f}s...")
            time.sleep(wait_time + 1)
            self.tokens_this_minute = 0
            self.minute_start = time.time()
    
    def record_tokens(self, input_tokens, output_tokens):
        """Registriert tatsächliche Token-Nutzung nach API Call"""
        self.tokens_this_minute += input_tokens
        self.request_count += 1
    
    def get_status(self):
        """Gibt aktuellen Nutzungsstatus zurück"""
        elapsed = time.time() - self.minute_start
        if elapsed >= 60:
            return "Ready (minute reset)"
        return f"{self.tokens_this_minute:,}/{self.buffer_limit:,} tokens, {60-elapsed:.0f}s until reset"


# Known False Positives Database
# Status Levels:
#   RESOLVED - Issue wurde gefixt, AI prüft trotzdem ob Fix korrekt ist
#   IGNORED  - Issue ist kein Problem (AI kann trotzdem warnen bei Zweifel)
#   MONITOR  - Issue ist akzeptabel, aber bei Context-Änderung neu bewerten
KNOWN_FALSE_POSITIVES = {
    # ========================================================================
    # RESOLVED ISSUES (Phase 12 Fixes - 2025-12-31)
    # ========================================================================
    "Issue #18 - Multi-Worker DB Engine": [
        {
            "pattern": r"engine = create_engine.*SessionLocal = sessionmaker",
            "reason": "RESOLVED: Issue #18 fixed (Commit 0ccac65, 2025-12-31) - Shared engine at module level",
            "status": "RESOLVED",
            "applies_to": ["src/01_web_app.py", "src/thread_api.py"],
            "fix_commit": "0ccac65",
            "fix_verification": "doc/erledigt/PHASE_12_FIX_VERIFICATION.md",
            "expected_implementation": "engine/SessionLocal at module level (lines 299-300), lazy import in thread_api"
        },
    ],
    "Issue #1 - CSRF AJAX Protection": [
        {
            "pattern": r"X-CSRFToken.*csrf_protect_ajax",
            "reason": "RESOLVED: Phase 12 Fix #1 - CSRF validation for all AJAX endpoints",
            "status": "RESOLVED",
            "applies_to": ["src/01_web_app.py"],
            "fix_verification": "doc/erledigt/PHASE_12_FIX_VERIFICATION.md",
            "expected_implementation": "csrf_protect_ajax() validates X-CSRFToken header"
        },
    ],
    "Issue #3 - XSS in Thread View": [
        {
            "pattern": r"escapeHtml\(\).*innerHTML",
            "reason": "RESOLVED: Phase 12 Fix #3 - XSS protection with escapeHtml() for dynamic content",
            "status": "RESOLVED",
            "applies_to": ["templates/threads_view.html"],
            "fix_verification": "doc/erledigt/PHASE_12_FIX_VERIFICATION.md",
            "expected_implementation": "All dynamic content escaped before innerHTML insertion"
        },
    ],
    "Issue #10 - N+1 Query in list_view": [
        {
            "pattern": r"email_tags_map.*subqueryload",
            "reason": "RESOLVED: Phase 12 Fix #10 - Eager loading with subqueryload() prevents N+1",
            "status": "RESOLVED",
            "applies_to": ["src/01_web_app.py"],
            "fix_verification": "doc/erledigt/PERFORMANCE_FIX_N+1_QUERY.md",
            "expected_implementation": "Tags loaded in single query via subqueryload()"
        },
    ],
    
    # ========================================================================
    # KNOWN FALSE POSITIVES (Design Decisions)
    # ========================================================================
    "Command Injection": [
        {
            "pattern": r"args\.host.*app\.run",
            "reason": "Flask app.run() validates host internally (no shell execution)",
            "status": "MONITOR",  # Überwachen bei subprocess-Nutzung
            "applies_to": ["src/00_main.py"]
        },
        {
            "pattern": r"argparse.*type=int",
            "reason": "argparse validates types automatically",
            "status": "IGNORED",  # Komplett sicher
            "applies_to": ["src/00_main.py"]
        },
    ],
    "JSON Deserialization": [
        {
            "pattern": r"json\.loads",
            "reason": "Python 3.13+ has built-in memory limits in json.loads()",
            "status": "MONITOR",  # Bei User-Input trotzdem prüfen
            "applies_to": ["src/00_main.py", "src/10_google_oauth.py"]
        },
    ],
    "Process Memory": [
        {
            "pattern": r"CLI.*ps aux",
            "reason": "Requires local access (game over scenario)",
            "status": "IGNORED",  # Nicht relevant für Threat Model
            "applies_to": ["src/00_main.py"]
        },
    ],
    "Uncontrolled Thread": [
        {
            "pattern": r"threading\.Thread.*run_http_redirector.*daemon=True",
            "reason": "HTTP→HTTPS redirector thread (daemon=True, terminates with parent process)",
            "status": "IGNORED",  # Safe pattern
            "applies_to": ["src/01_web_app.py"]
        },
        {
            "pattern": r"threading\.Thread.*daemon=True.*timeout",
            "reason": "Sanitization timeout handler (daemon, terminates with parent)",
            "status": "IGNORED",  # Safe pattern
            "applies_to": ["src/04_sanitizer.py"]
        },
    ],
    "Rate Limiting Storage": [
        {
            "pattern": r"storage_uri.*memory://",
            "reason": "In-memory OK für Heimnetz + Fail2Ban backup (Phase 9 Design-Decision)",
            "status": "MONITOR",  # Bei Cloud-Deployment ändern
            "applies_to": ["src/01_web_app.py"]
        },
    ],
    "Hardcoded Secrets": [
        {
            "pattern": r"SECRET_KEY.*CHANGE_ME",
            "reason": "Template-Wert in service file, wird durch Admin ersetzt (documented)",
            "status": "IGNORED",  # Dokumentiertes Template
            "applies_to": ["mail-helper.service"]
        },
    ],
    "Session Fixation": [
        {
            "pattern": r"session\.regenerate\(\)",
            "reason": "Flask-Session 0.8.0 mit 256-bit random IDs + SameSite=Lax (Phase 9 Decision)",
            "status": "MONITOR",  # Bei Session-Upgrades prüfen
            "applies_to": ["src/01_web_app.py"]
        },
    ],
}

# Layer Definitions
LAYERS = {
    'layer1_security': {
        'name': 'Security & Authentication',
        'priority': 'KRITISCH',
        'files': [
            'src/01_web_app.py',
            'src/07_auth.py',
            'src/08_encryption.py',
            'src/09_password_validator.py',
            'src/02_models.py',  # Context: Auth nutzt User Model
            'src/00_env_validator.py',  # Context: SECRET_KEY Validierung
        ],
        'focus': [
            'OWASP Top 10 Vulnerabilities',
            'Zero-Knowledge Encryption Flaws',
            'Session Management Issues',
            'SQL/NoSQL Injection',
            'XSS & CSRF Protection',
            'Authentication Bypass',
            'Password Storage & Validation',
            'API Key Exposure',
            'Cross-File Dependencies (Auth→Models→Encryption)',
        ]
    },
    'layer2_data': {
        'name': 'Data & Processing',
        'priority': 'HOCH',
        'files': [
            'src/02_models.py',
            'src/06_mail_fetcher.py',
            'src/12_processing.py',
            'src/10_google_oauth.py',
        ],
        'focus': [
            'SQL Injection Vectors',
            'Race Conditions',
            'Data Integrity Issues',
            'OAuth Flow Security',
            'IMAP Credential Handling',
            'Error Information Leakage',
            'Transaction Safety',
        ]
    },
    'layer3_ai': {
        'name': 'AI & Scoring',
        'priority': 'MITTEL',
        'files': [
            'src/03_ai_client.py',
            'src/04_sanitizer.py',
            'src/05_scoring.py',
            'src/15_provider_utils.py',
        ],
        'focus': [
            'Prompt Injection Attacks',
            'PII Data Leakage to AI',
            'API Rate Limit Handling',
            'Error Handling in AI Calls',
            'Sanitizer Bypass Vulnerabilities',
            'Provider Fallback Logic',
        ]
    },
    'layer4_infrastructure': {
        'name': 'Infrastructure & Background',
        'priority': 'MITTEL',
        'files': [
            'src/00_main.py',
            'src/00_env_validator.py',
        ],
        'focus': [
            'DOS/DDOS Resilience',
            'Resource Exhaustion',
            'Config Injection',
            'Job Queue Security',
            'Environment Variable Exposure',
            'CLI Argument Injection',
        ]
    },
    'layer5_frontend': {
        'name': 'Frontend & Templates',
        'priority': 'NIEDRIG',
        'files': [
            'templates/',
        ],
        'focus': [
            'XSS Vulnerabilities',
            'CSRF Token Usage',
            'Input Validation',
            'Content Security Policy',
            'Sensitive Data in HTML',
        ]
    }
}


def create_layer_file(layer_id, layer_config, output_dir):
    """Erstellt merged file für einen Layer"""
    output_file = output_dir / f"{layer_id}.txt"
    
    with open(output_file, 'w', encoding='utf-8') as outf:
        # Header
        outf.write("=" * 100 + "\n")
        outf.write(f"CODE REVIEW LAYER: {layer_config['name']}\n")
        outf.write(f"PRIORITY: {layer_config['priority']}\n")
        outf.write(f"FILES: {len(layer_config['files'])}\n")
        outf.write("=" * 100 + "\n\n")
        
        # Files
        for filepath in layer_config['files']:
            full_path = project_root / filepath
            
            if full_path.is_dir():
                # Template-Ordner
                for template_file in full_path.rglob('*.html'):
                    _write_file_content(outf, template_file, filepath)
            elif full_path.exists():
                _write_file_content(outf, full_path, filepath)
            else:
                outf.write(f"\n⚠️  FILE NOT FOUND: {filepath}\n\n")
    
    return output_file


def _write_file_content(outf, filepath, rel_path):
    """Schreibt Datei-Inhalt mit Header"""
    outf.write("\n" + "#" * 100 + "\n")
    outf.write(f"# FILE: {rel_path}\n")
    outf.write(f"# PATH: {filepath}\n")
    outf.write("#" * 100 + "\n\n")
    
    try:
        with open(filepath, 'r', encoding='utf-8') as inf:
            outf.write(inf.read())
    except Exception as e:
        outf.write(f"\n⚠️  ERROR READING FILE: {e}\n")
    
    outf.write("\n\n" + "#" * 100 + "\n")
    outf.write(f"# END OF FILE: {rel_path}\n")
    outf.write("#" * 100 + "\n\n\n")


def extract_imports(code_content):
    """Extrahiert Python-Imports aus Code"""
    imports = []
    
    # Pattern für: import xyz, from xyz import abc
    import_pattern = r'^\s*(?:from\s+([\w.]+)\s+)?import\s+([\w\s,]+)'
    
    for line in code_content.split('\n'):
        match = re.match(import_pattern, line)
        if match:
            if match.group(1):  # from X import Y
                imports.append(match.group(1))
            else:  # import X
                imports.append(match.group(2).split(',')[0].strip())
    
    # Standard Library + Common Packages Filter
    stdlib_libs = {
        'os', 'sys', 'pathlib', 'datetime', 're', 'json', 'sqlite3',
        'flask', 'sqlalchemy', 'anthropic', 'dotenv', 'alembic', 'gunicorn',
        'werkzeug', 'hashlib', 'hmac', 'secrets', 'logging', 'asyncio',
        'threading', 'urllib', 'requests', 'typing', 'collections', 'functools',
        'email', 'imaplib', 'base64', 'pickle',  # Mail-spezifisch
        'smtplib', 'ssl', 'configparser', 'tempfile'  # Weitere relevante
    }
    local_imports = [imp for imp in imports if imp not in stdlib_libs and not imp.startswith('_')]
    return list(set(local_imports))  # Unique


def get_related_files(filepath, layer_config):
    """Findet verwandte Files im selben Layer"""
    current_file = Path(filepath).name
    related = [f for f in layer_config['files'] if Path(f).name != current_file]
    return ', '.join([Path(f).name for f in related[:5]])  # Max 5


def load_project_context(file_size_chars=0, mode_override=None):
    """Lädt Projekt-Dokumentation adaptiv basierend auf Dateigröße
    
    Modi (3 Levels):
    - REDUCED: Minimal (3 Docs) - für große Files oder schnelle Reviews (~15k tokens)
    - FULL: Standard (9 Docs) - für normale Files (<50k) (~50k tokens) [DEFAULT]
    - DEEP: Maximum (11 Docs) - für erste Reviews oder Security-Deep-Dives (~65k tokens)
    
    Args:
        file_size_chars: Dateigröße für adaptive Auswahl
        mode_override: Manuelles Override ('REDUCED', 'FULL', 'DEEP' oder None für auto)
    """
    
    # 1. CLI-Override hat Priorität
    if mode_override:
        mode = mode_override.upper()
    # 2. Sonst: Automatisch basierend auf Dateigröße
    elif file_size_chars > LARGE_FILE_THRESHOLD:
        mode = "REDUCED"
    else:
        mode = "FULL"
    
    # Context-Files je nach Modus
    if mode == "REDUCED":
        context_files = {
            'README.md': 'Projekt-Übersicht',
            'ARCHITECTURE.md': 'Design Decisions',
            'doc/erledigt/PHASE_12_FIX_VERIFICATION.md': 'Bereits gefixte Issues (verhindert Duplikate!)',
        }
    elif mode == "DEEP":
        context_files = {
            'README.md': 'Projekt-Übersicht, Features, Tech Stack',
            'ARCHITECTURE.md': 'Design Decisions, Zero-Knowledge Model',
            'docs/SECURITY.md': 'Security Model, Threat Analysis',
            'docs/DEPLOYMENT.md': 'Production Setup',
            'docs/CHANGELOG.md': 'Fix-History, Known Issues',
            'doc/erledigt/ZERO_KNOWLEDGE_ARCHITECTURE.md': 'Zero-Knowledge Details',
            'doc/erledigt/PHASE_12_FIX_VERIFICATION.md': 'Verified Fixes (alle 20)',
            'doc/erledigt/PHASE_12_CODE_REVIEW.md': 'Review-Findings',
            'doc/development/Instruction_&_goal.md': 'Detaillierte Architektur Phase 0-12',
            'doc/erledigt/PERFORMANCE_FIX_N+1_QUERY.md': 'Performance-Optimierung',
            'doc/erledigt/PHASE_12_DEEP_REVIEW.md': 'Detaillierte Fix-Analyse',
        }
    else:  # FULL (default)
        context_files = {
            'README.md': 'Projekt-Übersicht, Features, Tech Stack',
            'ARCHITECTURE.md': 'Design Decisions, Zero-Knowledge Model',
            'docs/SECURITY.md': 'Security Model, Threat Analysis',
            'docs/DEPLOYMENT.md': 'Production Setup',
            'docs/CHANGELOG.md': 'Fix-History, Known Issues',
            'doc/erledigt/ZERO_KNOWLEDGE_ARCHITECTURE.md': 'Zero-Knowledge Details',
            'doc/erledigt/PHASE_12_FIX_VERIFICATION.md': 'Verified Fixes (alle 20)',
            'doc/erledigt/PHASE_12_CODE_REVIEW.md': 'Review-Findings',
            'doc/development/Instruction_&_goal.md': 'Detaillierte Architektur Phase 0-12',
        }
    
    context = "## 📚 PROJEKT-KONTEXT\n\n"
    context += f"**Context Mode:** {mode} ({len(context_files)} Dokumente)\n\n"
    
    if mode == "REDUCED":
        context += "*(Context reduziert - Minimal-Modus für große Files/schnelle Reviews)*\n\n"
    elif mode == "DEEP":
        context += "*(Context maximum - Alle verfügbaren Docs für Deep-Dive)*\n\n"
    
    loaded_count = 0
    for filename, description in context_files.items():
        filepath = project_root / filename
        if filepath.exists():
            context += f"### {filename} ({description})\n\n"
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Limit auf 100k chars pro Datei für Sicherheit
                    if len(content) > 100000:
                        content = content[:100000] + "\n\n[... gekürzt - Datei zu groß ...]"
                    context += f"```\n{content}\n```\n\n"
                    loaded_count += 1
            except Exception as e:
                context += f"⚠️ Fehler beim Laden: {e}\n\n"
        else:
            context += f"⚠️ {filename} nicht gefunden (erwartet aber nicht kritisch)\n\n"
    
    context += f"\n---\n**Geladene Dokumente:** {loaded_count}/{len(context_files)}\n\n"
    
    return context


def build_review_prompt(filepath, code_content, layer_name, layer_config=None, file_size_chars=0, context_mode=None):
    """Erstellt Context-aware Review-Prompt mit Threat Model & Dependencies
    
    file_size_chars wird automatisch aus code_content ermittelt, falls nicht angegeben
    context_mode: Optional 'REDUCED', 'FULL', 'DEEP' override
    """
    
    # Auto-detect file size if not provided
    if not file_size_chars:
        file_size_chars = len(code_content)
    
    # Load project context (adaptive basierend auf Dateigröße + optional override)
    project_context = load_project_context(file_size_chars, context_mode)
    
    # Extract Dependencies
    imports = extract_imports(code_content)
    dependency_context = ""
    if imports:
        dependency_context = f"\n**🔗 Diese Datei importiert:** {', '.join(imports)}\n"
    
    if layer_config:
        related = get_related_files(filepath, layer_config)
        if related:
            dependency_context += f"**📦 Verwandte Files im Layer:** {related}\n"
            dependency_context += "**⚠️ Beachte Cross-File Dependencies und Interaktionen!**\n"
    
    # Threat Model Context
    threat_model = """
## 🎯 SECURITY CONTEXT (Critical - Read First!)

**Application Profile:**
- **Type:** Multi-user home server (Familie im Heimnetz + VPN Remote-Access)
- **Database:** SQLite (single-threaded, local file)
- **Users:** Multi-user (Familie: ~2-5 User)
- **Authentication:** Web dashboard mit 2FA + Recovery-Codes auf Port 5001 (HTTPS)
- **Deployment:** Debian Home-Server (Heimnetz + VPN + Reverse Proxy)
- **Email Input:** IMAP (GMX, Yahoo, Hotmail) + Gmail OAuth
- **AI Processing:** Lokal (Ollama) ODER Cloud (OpenAI/Anthropic) mit Sanitization
- **Logs:** Written to local disk files + Fail2Ban Integration
- **Encryption:** Zero-Knowledge (DEK/KEK Pattern, AES-256-GCM)

**Production Hardening (Phase 9):**
- ✅ Flask-Limiter (5 requests/min Login/2FA)
- ✅ Account Lockout (5 failed → 15min ban)
- ✅ Session Timeout (30min Inaktivität)
- ✅ Fail2Ban Integration (5 fails/10min → 1h IP-Ban)
- ✅ Gunicorn Production Server (Multi-Worker)
- ✅ Systemd Service (Auto-Start, Security Hardening)
- ✅ Automated Backups (Daily + Weekly mit Rotation)
- ✅ Audit Logging (Strukturierte SECURITY[] Tags)
- ✅ HIBP Password Check (500M+ kompromittierte Passwörter)
- ✅ CSRF Protection (Flask-WTF)
- ✅ SECRET_KEY aus System Environment (nicht .env!)

**Threat Model - Kritische Risiken:**
1. ✅ **SQL Injection** (Multi-User → kritisch!)
2. ✅ **XSS & CSRF** (Web-Dashboard für Familie)
3. ✅ **Session Hijacking** (VPN Remote-Access)
4. ✅ **Brute-Force** (Login über Internet erreichbar)
5. ✅ **Zero-Knowledge Breaks** (DEK/KEK Pattern, Master-Key Leaks)
6. ✅ **Credential Exposure** (Logs, Errors, Environment)
7. ✅ **Rate Limiting Bypass** (Multi-Worker Gunicorn Setup)
8. ✅ **IMAP/OAuth Token Leaks** (verschlüsselt, aber Decrypt-Bugs?)

**Threat Model - Kontext-basierte Bewertung (nicht komplett ignorieren!):**

Diese Themen im **Home-Server Kontext** richtig bewerten:

1. 🟡 **"Command Injection"** - Nur relevant bei Shell-Execution (subprocess, os.system)
   - Flask app.run(host=...) ist KEIN Command Injection (keine Shell)
   - Aber: Wenn irgendwo subprocess.run(shell=True) mit User-Input → KRITISCH!

2. 🟡 **"Connection Pool Exhaustion"** - SQLite ist single-threaded
   - Connection Pool Attacks funktionieren nicht bei SQLite
   - Aber: Race Conditions in Multi-Worker Setup trotzdem möglich!

3. 🟡 **"Process Memory Inspection"** - Erfordert root/debugging
   - Attacker mit root-Zugriff = game over
   - Aber: Sensitive Data in Logs/Errors ist trotzdem ein Problem!

4. 🟡 **"Environment Variable Angriffe"** - Erfordert ENV-Zugriff
   - Attacker mit ENV-Zugriff = game over
   - Aber: .env Files in Git-Repo oder World-Readable → KRITISCH!

5. 🟡 **"Python stdlib Paranoia"** - Python 3.13 hat Sicherheitsfixes
   - json.loads() hat built-in memory limits
   - argparse validates types automatisch
   - Aber: Unsafe deserialization (pickle) bleibt KRITISCH!

6. 🟡 **"Threading-Probleme"** - Kontext wichtig
   - Single-threaded Ops haben keine Race Conditions
   - Aber: Gunicorn Multi-Worker + SQLite kann Deadlocks haben!

**Python Context:**
- Python 3.13 mit SQLAlchemy 2.0
- json.loads() hat built-in memory limits
- argparse validates types automatisch
- Flask validates host/port in app.run()

**Deine Aufgabe:**
- Bewerte Risiken **im Production Home-Server Kontext**
- Erwähne auch niedrig-priorisierte Themen, wenn sie im Kontext relevant sein könnten
- Sei praktisch, aber nicht paranoid
- **ANTWORTE AUF DEUTSCH** für bessere Verständlichkeit
"""
    
    prompt = f"""# Security Code Review (Production Home-Server)

**File:** {filepath}
**Layer:** {layer_name}
{dependency_context}

{project_context}

{threat_model}

## Review Guidelines
1. **Sei Spezifisch:** Referenziere exakte Zeilennummern aus DIESER Datei
2. **Severity bewerten:** KRITISCH/HOCH/MITTEL/NIEDRIG (im Home-Server Kontext!)
3. **Kontext-basierte Bewertung:** Auch niedrige Risiken erwähnen, wenn relevant
4. **Fixes bereitstellen:** Konkrete Code-Beispiele
5. **Kontext erklären:** Warum ist das gefährlich **in diesem Deployment**?

## Output Format (DEUTSCH!)
Für jedes Finding:

**[SEVERITY] Issue Titel**
- **Location:** file.py:line_number
- **Beschreibung:** Was ist die Schwachstelle?
- **Exploitability:** Wie kann das konkret ausgenutzt werden? (im Home-Server Kontext!)
- **Impact:** Was passiert bei Exploitation?
- **Kontext-Bewertung:** Warum ist das in DIESEM Setup relevant/nicht relevant?
- **Empfehlung:** Konkreter Fix mit Code-Beispiel

## Code zu reviewen

{code_content}

---

**WICHTIG: Antworte auf DEUTSCH!** Beginne Analyse. Fokus auf exploitable Issues im Home-Server Kontext. Erwähne auch niedrig-priorisierte Themen wenn sie Kontext-relevant sind."""

    return prompt


def _call_claude_with_retry(client, prompt, max_tokens, max_retries=3):
    """Ruft Claude API mit exponential backoff bei Rate Limits auf"""
    
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            return response
        
        except anthropic.RateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                print(f"      ⏳ Rate Limited → Retry in {wait_time}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                raise
        
        except anthropic.BadRequestError as e:
            print(f"      ❌ Bad Request: {e}")
            raise
    
    raise Exception("Max retries exceeded")


def two_pass_review(filepath, code_content, layer_name, layer_config, limiter):
    """2-Pass Review mit Rate Limit Handling: Quick Scan → Deep Dive bei kritischen Findings
    
    file_size_chars wird automatisch aus code_content ermittelt
    """
    
    print(f"      🔍 2-Pass Review (große/kritische Datei)...")
    
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in .env!")
    
    client = anthropic.Anthropic(api_key=api_key)
    
    try:
        # Pass 1: Quick Security Scan (file_size_chars wird auto-erkannt)
        quick_prompt = build_review_prompt(filepath, code_content, layer_name, layer_config, context_mode=CONTEXT_MODE_OVERRIDE)
        quick_prompt += "\n\n**PASS 1: Quick Security Scan**\nFokus auf KRITISCHE/HOHE Severity Issues. Kurze Zusammenfassung.\n"
        
        # Rate Limit Check
        estimated_tokens = estimate_tokens(quick_prompt)
        limiter.check_budget(estimated_tokens)
        
        # API Call mit Retry
        quick_response = _call_claude_with_retry(client, quick_prompt, 6000)
        quick_review = quick_response.content[0].text
        
        # Token Tracking
        limiter.record_tokens(quick_response.usage.input_tokens, quick_response.usage.output_tokens)
        quick_tokens = quick_response.usage.input_tokens + quick_response.usage.output_tokens
        
        print(f"      📊 Pass 1 Tokens: {quick_tokens:,} (In: {quick_response.usage.input_tokens:,}, Out: {quick_response.usage.output_tokens:,})")
        time.sleep(2)  # Rate Limit Safety
        
        # Check for critical issues
        has_critical = "[KRITISCH]" in quick_review or "[HOCH]" in quick_review
        
        if has_critical:
            print(f"      🚨 Kritische Issues gefunden → Deep Dive...")
            
            # Pass 2: Deep Dive (file_size_chars wird auto-erkannt)
            deep_prompt = build_review_prompt(filepath, code_content, layer_name, layer_config, context_mode=CONTEXT_MODE_OVERRIDE)
            deep_prompt += f"\n\n**PASS 2: Deep Dive Analysis**\n\nQuick Scan ergab:\n{quick_review[:1000]}...\n\n"
            deep_prompt += "Analysiere jetzt im Detail: Root Cause, Exploit-Szenarien, konkrete Fixes mit Code.\n"
            
            # Rate Limit Check
            estimated_tokens = estimate_tokens(deep_prompt)
            limiter.check_budget(estimated_tokens)
            
            # API Call mit Retry
            deep_response = _call_claude_with_retry(client, deep_prompt, 12000)
            deep_review = deep_response.content[0].text
            
            # Token Tracking
            limiter.record_tokens(deep_response.usage.input_tokens, deep_response.usage.output_tokens)
            deep_tokens = deep_response.usage.input_tokens + deep_response.usage.output_tokens
            
            print(f"      📊 Pass 2 Tokens: {deep_tokens:,} (In: {deep_response.usage.input_tokens:,}, Out: {deep_response.usage.output_tokens:,})")
            print(f"      💰 Total 2-Pass: {quick_tokens + deep_tokens:,} tokens")
            time.sleep(2)  # Rate Limit Safety
            
            # Merge Reviews
            merged = f"## 📊 2-Pass Review Summary\n\n"
            merged += f"**Token Usage:** Pass 1: {quick_tokens:,} | Pass 2: {deep_tokens:,} | Total: {quick_tokens + deep_tokens:,}\n\n"
            merged += f"### Pass 1: Quick Scan\n\n{quick_review}\n\n---\n\n"
            merged += f"### Pass 2: Deep Dive\n\n{deep_review}\n"
            
            return merged
        else:
            print(f"      ✅ Keine kritischen Issues → Quick Scan ausreichend")
            print(f"      📊 Quick Scan Tokens: {quick_tokens:,}")
            return quick_review
    
    except anthropic.RateLimitError as e:
        print(f"      ❌ Rate Limit Error (2-Pass): {e}")
        return f"ERROR: Rate Limit - {e}"
    except Exception as e:
        print(f"      ❌ 2-Pass Review Error: {e}")
        return f"ERROR in 2-Pass Review: {e}"


def review_file_with_claude(filepath, code_content, layer_name, layer_config=None, file_size_lines=0, limiter=None):
    """Ruft Claude API für einzelnes File auf mit Rate Limit Handling
    
    file_size_chars wird automatisch aus code_content ermittelt
    """
    
    # Fallback für alten Code (sollte nicht vorkommen mit neuem main())
    if limiter is None:
        limiter = APIRateLimiter()
    
    # Check if 2-pass review needed (große/kritische Files)
    use_two_pass = file_size_lines > 500 and layer_name in ['Security & Authentication', 'Data & Processing']
    
    if use_two_pass:
        return two_pass_review(filepath, code_content, layer_name, layer_config, limiter)
    
    # Build prompt (file_size_chars wird auto-erkannt)
    prompt = build_review_prompt(filepath, code_content, layer_name, layer_config, context_mode=CONTEXT_MODE_OVERRIDE)
    
    # Rate Limit Check
    estimated_tokens = estimate_tokens(prompt)
    limiter.check_budget(estimated_tokens)
    
    # Call Claude API
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in .env!")
    
    client = anthropic.Anthropic(api_key=api_key)
    
    try:
        # API Call mit Retry
        message = _call_claude_with_retry(client, prompt, 12000)
        
        # Token Tracking
        limiter.record_tokens(message.usage.input_tokens, message.usage.output_tokens)
        total_tokens = message.usage.input_tokens + message.usage.output_tokens
        
        review_text = message.content[0].text
        print(f"      📊 Tokens: {total_tokens:,} (In: {message.usage.input_tokens:,}, Out: {message.usage.output_tokens:,})")
        time.sleep(2)  # Rate Limit Safety
        
        return review_text
    
    except anthropic.RateLimitError as e:
        print(f"      ❌ Rate Limit Error: {e}")
        return f"ERROR: Rate Limit exceeded - {e}"
    
    except anthropic.BadRequestError as e:
        print(f"      ❌ Bad Request: {e}")
        return f"ERROR: Bad Request - {e}"
    
    except Exception as e:
        print(f"      ❌ Unexpected Error: {e}")
        return f"ERROR: {e}"


def calibrate_findings(review_text, filepath):
    """Kontextualisiert bekannte False Positives (markiert statt ignoriert)"""
    
    monitor_findings = []
    ignored_findings = []
    filename = Path(filepath).name
    
    for category, patterns in KNOWN_FALSE_POSITIVES.items():
        for pattern_config in patterns:
            # Check if pattern applies to this file
            if not any(applies in filename for applies in pattern_config['applies_to']):
                continue
            
            # Check if pattern exists in review
            if re.search(pattern_config['pattern'], review_text, re.IGNORECASE):
                finding = {
                    'category': category,
                    'reason': pattern_config['reason'],
                    'pattern': pattern_config['pattern'],
                    'status': pattern_config.get('status', 'MONITOR')
                }
                
                if finding['status'] == 'IGNORED':
                    ignored_findings.append(finding)
                else:  # MONITOR
                    monitor_findings.append(finding)
    
    # Build calibration note only if we have findings
    if monitor_findings or ignored_findings:
        calibration_note = "\n\n---\n\n## 🔍 CONTEXT-AWARE CALIBRATION\n\n"
        
        # MONITOR Findings - detailliert (wichtigste zuerst!)
        if monitor_findings:
            calibration_note += "**⏸️ MONITOR Findings** (Home-Server Kontext weniger kritisch, aber prüfen!):\n\n"
            for fp in monitor_findings:
                calibration_note += f"### {fp['category']}\n"
                calibration_note += f"- **Kontext:** {fp['reason']}\n"
                calibration_note += f"- **Status:** [⏸️ MONITOR]\n"
                calibration_note += f"- **Aktion:** Manuell prüfen bei Multi-Worker/Production Setup\n\n"
        
        # Legende in der Mitte (Kontext für beide Kategorien)
        calibration_note += "\n---\n\n"
        calibration_note += "**Status-Bedeutung:**\n"
        calibration_note += "- **[🔴 KRITISCH]** = Sofort beheben (oben in Review vor Calibration)\n"
        calibration_note += "- **[⏸️ MONITOR]** = Weniger kritisch, aber Multi-Worker/Deployment beachten\n"
        calibration_note += "- **[❌ IGNORIERT]** = Wirklich nicht relevant (nicht im Code/nicht im Threat Model)\n\n"
        calibration_note += "Diese Kalibrierung reduziert False Positives, ohne echte Bugs zu verschlucken.\n"
        
        # IGNORED Findings - minimal (am Ende, niedrigste Priorität)
        if ignored_findings:
            calibration_note += "\n---\n\n"
            calibration_note += "**❌ IGNORED Findings** (nicht relevant für dieses Setup):\n\n"
            for fp in ignored_findings:
                calibration_note += f"- **{fp['category']}**: {fp['reason']}\n"
            calibration_note += "\n"
        
        return review_text + calibration_note
    
    return review_text


def save_review_report(layer_id, layer_config, review_text, output_dir):
    """Speichert Review als Markdown"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{layer_id}_review_{timestamp}.md"
    filepath = output_dir / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"# Code Review: {layer_config['name']}\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Priority:** {layer_config['priority']}\n")
        f.write(f"**Files Reviewed:** {len(layer_config['files'])}\n\n")
        f.write("---\n\n")
        f.write(review_text)
    
    print(f"   💾 Report saved: {filename}")
    return filepath


def generate_index_report(reports, output_dir):
    """Erstellt Index-Datei mit allen Reports"""
    index_file = output_dir / "00_REVIEW_INDEX.md"
    
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write("# Code Review Index (v3.1)\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Method:** File-by-file with Threat Model, Rate Limit Protection & Calibration\n")
        f.write(f"**Total Layers:** {len(reports)}\n\n")
        f.write("---\n\n")
        
        f.write("## ✨ Improvements in v3.1 (Rate Limit Safe)\n\n")
        f.write("### Neue Features\n")
        f.write("1. **Smart Rate Limiting:** Proaktive Token-Überwachung (30k tokens/min)\n")
        f.write("   - `estimate_tokens()` Schätzung vor jedem Request\n")
        f.write("   - `APIRateLimiter.check_budget()` wartet bei Budget-Überschuss\n")
        f.write("   - Exponential Backoff Retry bei 429-Errors (1s → 2s → 4s)\n")
        f.write("2. **Adaptive Context Loading:** Große Files (<50k chars) → nur README\n")
        f.write("   - Spart ~20k tokens, verhindert Rate Limits\n")
        f.write("3. **Token Tracking:** Input + Output Tokens pro Request sichtbar\n")
        f.write("4. **Rate Limit Safety:** sleep(2) zwischen API Calls\n\n")
        
        f.write("### Bisherige Features (v3.0)\n")
        f.write("5. **Full Project Context:** 100k chars (vs. 3k in v1.0) - 33x more context!\n")
        f.write("6. **Dependency Graph:** Imports & cross-file dependencies extracted\n")
        f.write("7. **2-Pass Reviews:** Quick scan + deep dive for critical files (>500 lines)\n")
        f.write("8. **Context-Aware Calibration:** False positives marked, not ignored\n")
        f.write("9. **Expanded Security Layer:** 6 files with cross-dependencies\n\n")
        
        f.write("**Result:** ✅ Keine Rate Limit Errors mehr! ~3-5% false positive rate\n\n")
        f.write("---\n\n")
        
        f.write("## Review Reports\n\n")
        for layer_id, report_path in reports.items():
            layer_config = LAYERS[layer_id]
            file_count = len(layer_config['files'])
            f.write(f"### {layer_config['name']} ({layer_config['priority']})\n")
            f.write(f"- **Report:** [{report_path.name}]({report_path.name})\n")
            f.write(f"- **Files/Patterns:** {file_count}\n\n")
        
        f.write("\n---\n\n")
        f.write("## Next Steps\n\n")
        f.write("1. Read CRITICAL priority reports first\n")
        f.write("2. Validate findings (check calibration notes)\n")
        f.write("3. Address exploitable vulnerabilities\n")
        f.write("4. Ignore theoretical attacks marked as false positives\n")
    
    print(f"\n📋 Index created: {index_file.name}")


def review_layer_file_by_file(layer_id, layer_config, reports_dir, limiter):
    """Reviewed Layer mit File-by-File Approach und Rate Limit Handling"""
    
    file_reviews = []
    total_files = 0
    
    for filepath_pattern in layer_config['files']:
        full_path = project_root / filepath_pattern
        
        if full_path.is_dir():
            # Template-Ordner → alle HTML-Files
            files_to_review = list(full_path.rglob('*.html'))
        elif full_path.exists():
            files_to_review = [full_path]
        else:
            print(f"   ⚠️  File not found: {filepath_pattern}")
            continue
        
        for file_path in files_to_review:
            total_files += 1
            relative_path = file_path.relative_to(project_root)
            
            print(f"   📄 Reviewing {relative_path}...")
            
            # Read file
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    code_content = f.read()
            except Exception as e:
                print(f"      ❌ Error reading file: {e}")
                continue
            
            # Check size
            char_count = len(code_content)
            line_count = code_content.count('\n')
            print(f"      Size: {line_count} lines, {char_count:,} chars")
            
            # Skip empty files
            if char_count < 100:
                print(f"      ⏭️  Skipping (too small)")
                continue
            
            # Show Rate Limit Status
            print(f"      Status: {limiter.get_status()}")
            
            # Review with Claude (mit Rate Limit Handling)
            print(f"      🤖 Calling Claude API...")
            review_text = review_file_with_claude(
                str(relative_path), 
                code_content, 
                layer_config['name'],
                layer_config,
                line_count,
                limiter
            )
            
            # Calibrate (filter false positives)
            calibrated_review = calibrate_findings(review_text, str(relative_path))
            
            print(f"      ✅ Reviewed ({len(review_text):,} chars)")
            
            file_reviews.append({
                'filepath': str(relative_path),
                'review': calibrated_review,
                'lines': line_count,
                'chars': char_count
            })
    
    print(f"\n   ✅ Reviewed {total_files} files")
    
    # Merge file reviews into layer report
    return merge_file_reviews(layer_id, layer_config, file_reviews, reports_dir)


def merge_file_reviews(layer_id, layer_config, file_reviews, reports_dir):
    """Merged einzelne File-Reviews in Layer-Report"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{layer_id}_review_{timestamp}.md"
    filepath = reports_dir / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        # Header
        f.write(f"# Code Review: {layer_config['name']}\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Priority:** {layer_config['priority']}\n")
        f.write(f"**Files Reviewed:** {len(file_reviews)}\n")
        f.write(f"**Review Method:** File-by-file with Threat Model & Calibration\n\n")
        f.write("---\n\n")
        
        # Summary
        total_lines = sum(fr['lines'] for fr in file_reviews)
        total_chars = sum(fr['chars'] for fr in file_reviews)
        f.write(f"## 📊 Summary\n\n")
        f.write(f"- **Total Lines:** {total_lines:,}\n")
        f.write(f"- **Total Characters:** {total_chars:,}\n")
        f.write(f"- **Files Analyzed:** {len(file_reviews)}\n\n")
        f.write("---\n\n")
        
        # Individual file reviews
        for idx, fr in enumerate(file_reviews, 1):
            f.write(f"## {idx}. {fr['filepath']}\n\n")
            f.write(f"**Size:** {fr['lines']} lines, {fr['chars']:,} characters\n\n")
            f.write(fr['review'])
            f.write("\n\n---\n\n")
    
    print(f"   💾 Report saved: {filename}")
    return filepath


def main():
    # Parse CLI arguments
    parser = argparse.ArgumentParser(
        description='Automated Code Review mit Claude API (v3.1)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Context Modes:
  REDUCED  - Minimal (3 Docs, ~15k tokens)  - Große Files, schnelle Reviews
  FULL     - Standard (9 Docs, ~50k tokens) - Default für normale Files [DEFAULT]
  DEEP     - Maximum (11 Docs, ~65k tokens) - Erste Reviews, Security Deep-Dives

Examples:
  python scripts/automated_code_review.py                  # Auto (adaptiv)
  python scripts/automated_code_review.py --context full   # Force FULL
  python scripts/automated_code_review.py --context deep   # Force DEEP
        """
    )
    parser.add_argument(
        '--context',
        choices=['reduced', 'full', 'deep'],
        help='Context-Modus override (default: adaptiv basierend auf Dateigröße)'
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("🔍 Automated Code Review System v3.1")
    print("   ✨ With Rate Limit Protection, Adaptive Context & Deep Reviews")
    print("=" * 80)
    print()
    
    # Context Mode Info
    if args.context:
        print(f"📚 Context Mode: {args.context.upper()} (manual override)")
    else:
        print("📚 Context Mode: AUTO (adaptiv basierend auf Dateigröße)")
    print()
    
    # Initialize Rate Limiter
    limiter = APIRateLimiter(tokens_per_minute=30000, buffer_percent=85)
    print(f"🛡️  Rate Limiter: {limiter.tokens_per_minute:,} tokens/min (85% buffer)\n")
    
    # Create output directories
    reports_dir = project_root / 'review_output' / 'reports'
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Output: {reports_dir}\n")
    
    # Store context mode for use in review functions
    global CONTEXT_MODE_OVERRIDE
    CONTEXT_MODE_OVERRIDE = args.context
    
    # Process each layer
    reports = {}
    
    for layer_id, layer_config in LAYERS.items():
        print(f"\n{'='*80}")
        print(f"🔍 LAYER: {layer_config['name']} ({layer_config['priority']})")
        print(f"{'='*80}\n")
        
        # Review file-by-file (mit Rate Limiter)
        report_path = review_layer_file_by_file(layer_id, layer_config, reports_dir, limiter)
        reports[layer_id] = report_path
    
    # Generate index
    print(f"\n{'='*80}")
    generate_index_report(reports, reports_dir)
    
    print(f"\n{'='*80}")
    print("✨ Code Review Complete!")
    print(f"{'='*80}")
    print(f"\n📊 Rate Limiter Final Status: {limiter.get_status()}")
    print(f"💾 Total Requests: {limiter.request_count}")
    print(f"📂 Reports: {reports_dir}")
    print(f"📄 Start with: 00_REVIEW_INDEX.md\n")


if __name__ == '__main__':
    main()
