#!/usr/bin/env python3
"""
Automated Code Review mit Claude API
=====================================
5-Layer Deep Review System für vollständige Security & Architektur-Analyse
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import anthropic
from dotenv import load_dotenv

# Load .env
project_root = Path(__file__).parent.parent
load_dotenv(project_root / '.env')

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


def build_review_prompt(layer_config, code_content):
    """Erstellt Layer-spezifischen Review-Prompt"""
    focus_points = "\n".join(f"- {point}" for point in layer_config['focus'])
    
    prompt = f"""# Deep Security & Architecture Review

**Layer:** {layer_config['name']}
**Priority:** {layer_config['priority']}

## Your Task
You are a senior security auditor and software architect. Perform a comprehensive code review focusing on the following aspects:

{focus_points}

## Review Guidelines
1. **Be Thorough:** Check every function, route, and data flow
2. **Be Specific:** Reference exact line numbers and code snippets
3. **Prioritize:** Rate findings as CRITICAL, HIGH, MEDIUM, LOW
4. **Provide Solutions:** Include concrete fix recommendations with code examples
5. **Think Adversarially:** Consider how an attacker would exploit vulnerabilities

## Output Format
Structure your review as follows:

### 1. Executive Summary
- Overall security posture (0-100 score)
- Top 3 critical findings
- Risk assessment

### 2. Detailed Findings
For each issue:
```
**[SEVERITY] Issue Title**
- Location: file.py:123-456
- Description: What is the vulnerability?
- Impact: What could an attacker do?
- Proof of Concept: How to exploit it?
- Recommendation: How to fix it (with code)?
```

### 3. Architectural Concerns
- Design patterns that could cause issues
- Cross-layer dependencies
- Performance/scalability concerns

### 4. Positive Observations
- Well-implemented security features
- Good practices worth highlighting

### 5. Action Items
Prioritized list of fixes (CRITICAL first)

---

## Code to Review

{code_content}

---

Begin your deep analysis now. Be brutally honest - this is production code."""

    return prompt


def review_with_claude(layer_id, layer_config, layer_file):
    """Ruft Claude API für Review auf"""
    print(f"📝 Reviewing {layer_config['name']}...")
    
    # Read layer file
    with open(layer_file, 'r', encoding='utf-8') as f:
        code_content = f.read()
    
    # Check size
    char_count = len(code_content)
    token_estimate = char_count // 4
    print(f"   Code: {char_count:,} chars (~{token_estimate:,} tokens)")
    
    if token_estimate > 180000:
        print(f"   ⚠️  WARNING: Code might be too large for Claude!")
    
    # Build prompt
    prompt = build_review_prompt(layer_config, code_content)
    
    # Call Claude API
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in .env!")
    
    client = anthropic.Anthropic(api_key=api_key)
    
    print(f"   🤖 Calling Claude API...")
    
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",  # Claude Sonnet 4 (neuestes Modell!)
            max_tokens=8000,  # Lange Antworten erlauben
            temperature=0.3,  # Deterministisch für Reviews
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        review_text = message.content[0].text
        
        print(f"   ✅ Review completed ({len(review_text):,} chars)")
        
        return review_text
    
    except anthropic.BadRequestError as e:
        print(f"   ❌ API Error: {e}")
        return f"ERROR: {e}"
    
    except Exception as e:
        print(f"   ❌ Unexpected Error: {e}")
        return f"ERROR: {e}"


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
        f.write("# Code Review Index\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Total Layers:** {len(reports)}\n\n")
        f.write("---\n\n")
        
        f.write("## Review Reports\n\n")
        for layer_id, report_path in reports.items():
            layer_config = LAYERS[layer_id]
            f.write(f"### {layer_config['name']} ({layer_config['priority']})\n")
            f.write(f"- **Report:** [{report_path.name}]({report_path.name})\n")
            f.write(f"- **Files:** {', '.join(layer_config['files'])}\n\n")
        
        f.write("\n---\n\n")
        f.write("## Next Steps\n\n")
        f.write("1. Read CRITICAL priority reports first\n")
        f.write("2. Address all CRITICAL findings before deployment\n")
        f.write("3. Schedule fixes for HIGH priority issues\n")
        f.write("4. Review MEDIUM/LOW findings for long-term improvements\n")
    
    print(f"\n📋 Index created: {index_file.name}")


def main():
    print("=" * 80)
    print("🔍 Automated Code Review System")
    print("=" * 80)
    print()
    
    # Create output directories
    layer_files_dir = project_root / 'review_output' / 'layer_files'
    reports_dir = project_root / 'review_output' / 'reports'
    layer_files_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Output: {reports_dir}\n")
    
    # Process each layer
    reports = {}
    
    for layer_id, layer_config in LAYERS.items():
        print(f"\n{'='*80}")
        print(f"🔍 LAYER: {layer_config['name']} ({layer_config['priority']})")
        print(f"{'='*80}\n")
        
        # 1. Create merged file
        print(f"📦 Merging {len(layer_config['files'])} files...")
        layer_file = create_layer_file(layer_id, layer_config, layer_files_dir)
        print(f"   ✅ Created: {layer_file.name}")
        
        # 2. Review with Claude
        review_text = review_with_claude(layer_id, layer_config, layer_file)
        
        # 3. Save report
        report_path = save_review_report(layer_id, layer_config, review_text, reports_dir)
        reports[layer_id] = report_path
    
    # 4. Generate index
    print(f"\n{'='*80}")
    generate_index_report(reports, reports_dir)
    
    print(f"\n{'='*80}")
    print("✨ Code Review Complete!")
    print(f"{'='*80}")
    print(f"\n📂 Reports: {reports_dir}")
    print(f"📄 Start with: 00_REVIEW_INDEX.md\n")


if __name__ == '__main__':
    main()
