#!/usr/bin/env python3
"""
Test: Newsletter-Erkennung
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.optimized_reply_prompts import _detect_email_type, _get_type_specific_hint

# GMX Newsletter (dein Beispiel)
gmx_newsletter = {
    "subject": "GMX Update für Sie",
    "body": """Hallo Frau Weber, in ihrem GMX Update für Sie: Neue Features & Sicher­heits-Up­dates...
    
Bei dieser E-Mail handelt es sich um eine automatisch versendete Nachricht. 
Eine Antwort auf diese E-Mail ist nicht möglich, da die Absenderadresse nur zum Nachrichtenversand eingerichtet ist. 
Das GMX Magazin ist ein fester Leistungs­bestandteil des FreeMail Postfaches und kann nicht abbestellt werden.

Impressum https://www.gmx.net/impressum/
© 1&1 Mail & Media GmbH"""
}

# Normale Anfrage
normal_request = {
    "subject": "Angebot gewünscht",
    "body": "Können Sie mir ein Angebot schicken?"
}

# Frage
question = {
    "subject": "Frage zum Termin",
    "body": "Können wir den Termin verschieben?"
}

print("=" * 80)
print("NEWSLETTER-ERKENNUNG TEST")
print("=" * 80)

tests = [
    ("GMX Newsletter", gmx_newsletter),
    ("Normale Anfrage", normal_request),
    ("Frage", question)
]

for name, email in tests:
    detected = _detect_email_type(email["subject"], email["body"])
    hint = _get_type_specific_hint(detected)
    
    print(f"\n{name}:")
    print(f"  Typ erkannt: {detected}")
    
    if detected == "newsletter":
        print(f"  ✅ Als Newsletter erkannt!")
        print(f"  Hinweis: {hint[:100]}...")
    else:
        print(f"  ℹ️  Normaler Typ: {detected}")

print("\n" + "=" * 80)
if _detect_email_type(gmx_newsletter["subject"], gmx_newsletter["body"]) == "newsletter":
    print("✅ TEST BESTANDEN - GMX Newsletter wird erkannt!")
else:
    print("❌ TEST FEHLGESCHLAGEN - Newsletter nicht erkannt")
print("=" * 80)
