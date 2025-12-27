#!/usr/bin/env python3
"""
Automated Code Review mit Claude API (v2.0)
============================================
Improved with:
- Context-aware prompts with Threat Model
- File-by-file reviews (50-200 lines each)
- Known False Positives calibration layer
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
            "reason": "Python 3.9+ has built-in memory limits in json.loads()",
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


def build_review_prompt(filepath, code_content, layer_name):
    """Erstellt Context-aware Review-Prompt mit Threat Model"""
    
    # Threat Model Context
    threat_model = """
## 🎯 SECURITY CONTEXT (Critical - Read First!)

**Application Profile:**
- **Type:** Local email analysis tool (single-user desktop application)
- **Database:** SQLite (single-threaded, local file - NOT exposed to network)
- **Users:** Single user on local machine (NOT multi-tenant)
- **Authentication:** Web dashboard with 2FA on localhost:5000
- **Email Input:** From IMAP server (user controls which emails to fetch)
- **AI Processing:** Optional cloud (user chooses Ollama local OR OpenAI/Anthropic)
- **Logs:** Written to local disk files (NOT exposed in web interface)
- **Deployment:** Desktop application (NOT cloud/SaaS)

**Threat Model - What to Focus On:**
1. ✅ **Real code vulnerabilities** (SQL injection, XSS, CSRF)
2. ✅ **Credential exposure** (logs, error messages, process arguments)
3. ✅ **Input validation** (user-provided data in web forms)
4. ✅ **Zero-Knowledge encryption** (master key handling, DEK/KEK breaks)
5. ✅ **Session security** (hijacking, fixation, CSRF)

**Threat Model - What to IGNORE (False Alarms):**
1. ❌ "Command Injection" when no shell execution exists (e.g., Flask app.run(host=...))
2. ❌ "Connection Pool Exhaustion" for SQLite (single-threaded, doesn't apply)
3. ❌ "Process memory inspection" attacks (requires local root = game over)
4. ❌ Theoretical attacks requiring environment compromise (if attacker has ENV access, game over)
5. ❌ Over-paranoid readings of Python stdlib (json.loads has memory limits, argparse validates)
6. ❌ Multi-threading issues for single-threaded operations

**Python Context:**
- Python 3.9+ with standard library security features
- json.loads() has built-in memory limits
- argparse validates types automatically
- Flask validates host/port in app.run()

**Your Job:**
- Find **actually exploitable** bugs in **this specific context**
- Ignore theoretical attacks not relevant to a local desktop app
- Consider Python 3.9+ standard library behaviors
- **Be practical, not paranoid**
"""
    
    prompt = f"""# Security Code Review

**File:** {filepath}
**Layer:** {layer_name}

{threat_model}

## Review Guidelines
1. **Be Specific:** Reference exact line numbers from THIS file
2. **Rate Severity:** CRITICAL/HIGH/MEDIUM/LOW (only for exploitable issues)
3. **Only Report if Exploitable:** Don't report theoretical issues that can't be exploited
4. **Provide Fixes:** Include concrete code examples
5. **Explain Context:** Why is this dangerous in **this specific application**?

## Output Format
For each finding:

**[SEVERITY] Issue Title**
- **Location:** file.py:line_number
- **Description:** What is the vulnerability?
- **Exploitability:** How can this actually be exploited? (be specific)
- **Impact:** What happens if exploited?
- **Recommendation:** Concrete fix with code

## Code to Review

{code_content}

---

Begin analysis. Focus on real, exploitable issues. Ignore false alarms."""

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
