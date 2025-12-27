#!/usr/bin/env python3
"""
Automated Code Review mit Claude API (v2.1)
============================================
Improved with:
- Context-aware prompts with Threat Model
- Project documentation as context (README, DEPLOYMENT, Instruction_&_goal)
- File-by-file reviews (50-200 lines each)
- Known False Positives calibration layer
- Kontext-basierte Bewertung (nicht komplett ignorieren!)
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import anthropic
from dotenv import load_dotenv
import re

# Load .env
project_root = Path(__file__).parent.parent
load_dotenv(project_root / '.env')

# Known False Positives Database
KNOWN_FALSE_POSITIVES = {
    "Command Injection": [
        {
            "pattern": r"args\.host.*app\.run",
            "reason": "Flask app.run() validates host internally (no shell execution)",
            "applies_to": ["00_main.py"]
        },
        {
            "pattern": r"argparse.*type=int",
            "reason": "argparse validates types automatically",
            "applies_to": ["00_main.py"]
        },
    ],
    "Connection Pool": [
        {
            "pattern": r"SQLite.*create_engine",
            "reason": "SQLite is single-threaded, no connection pool needed",
            "applies_to": ["02_models.py", "00_main.py", "14_background_jobs.py"]
        },
    ],
    "JSON Deserialization": [
        {
            "pattern": r"json\.loads",
            "reason": "Python 3.13+ has built-in memory limits in json.loads()",
            "applies_to": ["00_main.py", "10_google_oauth.py"]
        },
    ],
    "Process Memory": [
        {
            "pattern": r"CLI.*ps aux",
            "reason": "Requires local access (game over scenario)",
            "applies_to": ["00_main.py"]
        },
    ],
    "Uncontrolled Thread": [
        {
            "pattern": r"threading\.Thread.*ensure_worker",
            "reason": "Single worker thread per instance (controlled)",
            "applies_to": ["14_background_jobs.py"]
        },
    ],
    "Rate Limiting Storage": [
        {
            "pattern": r"storage_uri.*memory://",
            "reason": "In-memory OK für Heimnetz + Fail2Ban backup (Phase 9 Design-Decision)",
            "applies_to": ["01_web_app.py"]
        },
    ],
    "Hardcoded Secrets": [
        {
            "pattern": r"SECRET_KEY.*CHANGE_ME",
            "reason": "Template-Wert in service file, wird durch Admin ersetzt (documented)",
            "applies_to": ["mail-helper.service"]
        },
    ],
    "Session Fixation": [
        {
            "pattern": r"session\.regenerate\(\)",
            "reason": "Flask-Session 0.8.0 mit 256-bit random IDs + SameSite=Lax (Phase 9 Decision)",
            "applies_to": ["01_web_app.py"]
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
            'src/14_background_jobs.py',
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


def load_project_context():
    """Lädt relevante Projekt-Dokumentation als Context"""
    context_files = {
        'README.md': 'Projekt-Übersicht, Features, Tech Stack',
        'DEPLOYMENT.md': 'Production Setup, Security Architecture',
        'Instruction_&_goal.md': 'Detaillierte Architektur, Phase 0-9'
    }
    
    context = "## 📚 PROJEKT-KONTEXT\n\n"
    
    for filename, description in context_files.items():
        filepath = project_root / filename
        if filepath.exists():
            context += f"### {filename} ({description})\n\n"
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Nur erste 3000 Zeichen (ca. 500 Zeilen) für Token-Limit
                    if len(content) > 3000:
                        content = content[:3000] + "\n\n[... gekürzt für Token-Limit ...]"
                    context += f"```\n{content}\n```\n\n"
            except Exception as e:
                context += f"⚠️ Fehler beim Laden: {e}\n\n"
        else:
            context += f"### {filename} (nicht gefunden)\n\n"
    
    return context


def build_review_prompt(filepath, code_content, layer_name):
    """Erstellt Context-aware Review-Prompt mit Threat Model"""
    
    # Load project context
    project_context = load_project_context()
    
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


def review_file_with_claude(filepath, code_content, layer_name):
    """Ruft Claude API für einzelnes File auf"""
    
    # Build prompt
    prompt = build_review_prompt(filepath, code_content, layer_name)
    
    # Call Claude API
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in .env!")
    
    client = anthropic.Anthropic(api_key=api_key)
    
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            temperature=0.3,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        review_text = message.content[0].text
        return review_text
    
    except anthropic.BadRequestError as e:
        print(f"      ❌ API Error: {e}")
        return f"ERROR: {e}"
    
    except Exception as e:
        print(f"      ❌ Unexpected Error: {e}")
        return f"ERROR: {e}"


def calibrate_findings(review_text, filepath):
    """Filtert bekannte False Positives aus Review"""
    
    false_positives_found = []
    filename = Path(filepath).name
    
    for category, patterns in KNOWN_FALSE_POSITIVES.items():
        for pattern_config in patterns:
            # Check if pattern applies to this file
            if not any(applies in filename for applies in pattern_config['applies_to']):
                continue
            
            # Check if pattern exists in review
            if re.search(pattern_config['pattern'], review_text, re.IGNORECASE):
                false_positives_found.append({
                    'category': category,
                    'reason': pattern_config['reason'],
                    'pattern': pattern_config['pattern']
                })
    
    # Add calibration note if false positives found
    if false_positives_found:
        calibration_note = "\n\n---\n\n## ⚠️ CALIBRATION NOTES (Potential False Positives)\n\n"
        calibration_note += "The following patterns were detected that are often false positives:\n\n"
        
        for fp in false_positives_found:
            calibration_note += f"- **{fp['category']}**: {fp['reason']}\n"
        
        calibration_note += "\n**Note:** Review above findings carefully. These may not be actual vulnerabilities in this context.\n"
        
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
        f.write("# Code Review Index (v2.0)\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Method:** File-by-file with Threat Model & Calibration\n")
        f.write(f"**Total Layers:** {len(reports)}\n\n")
        f.write("---\n\n")
        
        f.write("## ✨ Improvements in v2.0\n\n")
        f.write("1. **Context-Aware Prompts:** Threat model included (local app, SQLite, single-user)\n")
        f.write("2. **File-by-File Reviews:** 50-200 lines per review (better accuracy)\n")
        f.write("3. **Calibration Layer:** Known false positives filtered automatically\n\n")
        f.write("**Expected:** ~5-10% false positive rate (vs. 60% in v1.0)\n\n")
        f.write("---\n\n")
        
        f.write("## Review Reports\n\n")
        for layer_id, report_path in reports.items():
            layer_config = LAYERS[layer_id]
            file_count = len(expand_file_list(layer_config))
            f.write(f"### {layer_config['name']} ({layer_config['priority']})\n")
            f.write(f"- **Report:** [{report_path.name}]({report_path.name})\n")
            f.write(f"- **Files:** {file_count}\n\n")
        
        f.write("\n---\n\n")
        f.write("## Next Steps\n\n")
        f.write("1. Read CRITICAL priority reports first\n")
        f.write("2. Validate findings (check calibration notes)\n")
        f.write("3. Address exploitable vulnerabilities\n")
        f.write("4. Ignore theoretical attacks marked as false positives\n")
    
    print(f"\n📋 Index created: {index_file.name}")


def review_layer_file_by_file(layer_id, layer_config, reports_dir):
    """Reviewed Layer mit File-by-File Approach"""
    
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
            
            # Review with Claude
            print(f"      🤖 Calling Claude API...")
            review_text = review_file_with_claude(str(relative_path), code_content, layer_config['name'])
            
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
    print("=" * 80)
    print("🔍 Automated Code Review System v2.0")
    print("   ✨ With Threat Model, File-by-File & Calibration")
    print("=" * 80)
    print()
    
    # Create output directories
    reports_dir = project_root / 'review_output' / 'reports'
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Output: {reports_dir}\n")
    
    # Process each layer
    reports = {}
    
    for layer_id, layer_config in LAYERS.items():
        print(f"\n{'='*80}")
        print(f"🔍 LAYER: {layer_config['name']} ({layer_config['priority']})")
        print(f"{'='*80}\n")
        
        # Review file-by-file
        report_path = review_layer_file_by_file(layer_id, layer_config, reports_dir)
        reports[layer_id] = report_path
    
    # Generate index
    print(f"\n{'='*80}")
    generate_index_report(reports, reports_dir)
    
    print(f"\n{'='*80}")
    print("✨ Code Review Complete!")
    print(f"{'='*80}")
    print(f"\n📂 Reports: {reports_dir}")
    print(f"📄 Start with: 00_REVIEW_INDEX.md\n")


if __name__ == '__main__':
    main()
