"""
OPTIMIERTE REPLY-PROMPTS für KI-Mail-Helper
============================================

Basierend auf deinen Insights:
1. Es ist IMMER eine Antwort an jemanden
2. Nimmt IMMER Bezug auf Fragen oder bestätigt Erhalt
3. Klare E-Mail-Konventionen

VORHER: Generischer Prompt → LLM ist verwirrt
NACHHER: Strukturierter, kontextbewusster Prompt → bessere Qualität
"""

# ============================================================================
# SYSTEM-PROMPT (Global für alle Antworten)
# ============================================================================

REPLY_GENERATION_SYSTEM_PROMPT_OPTIMIZED = """Du bist ein professioneller E-Mail-Assistent der Antwort-Entwürfe erstellt.

KONTEXT:
- Du schreibst IMMER eine Antwort auf eine erhaltene E-Mail
- Der Empfänger ist der Absender der Original-E-Mail
- Die Antwort soll hilfreich, präzise und angemessen sein

DEINE AUFGABE:
Erstelle einen E-Mail-Antwort-Entwurf basierend auf:
1. Dem Inhalt der Original-E-Mail
2. Den vorgegebenen Ton-Anweisungen
3. Den E-Mail-Konventionen (Anrede, Bezug, Gruss)

WICHTIGE REGELN:
✅ Schreibe NUR den E-Mail-Body (OHNE Betreffzeile, OHNE "Von:", OHNE "An:")
✅ Beginne IMMER mit einer passenden Anrede
✅ Beziehe dich DIREKT auf den Inhalt der Original-E-Mail
✅ Beantworte gestellte Fragen oder bestätige den Erhalt
✅ Ende mit einer passenden Grussformel
✅ Halte den vorgegebenen Ton ein

❌ Wiederhole NICHT die Original-E-Mail
❌ Erfinde KEINE Informationen die nicht gegeben sind
❌ Schreibe KEINE Meta-Kommentare wie "Hier ist die Antwort..."
❌ Füge KEINE Betreffzeile hinzu
"""

# ============================================================================
# TON-SPEZIFISCHE PROMPTS (Optimiert)
# ============================================================================

TONE_PROMPTS_OPTIMIZED = {
    "formal": {
        "name": "Formell",
        "icon": "📜",
        "instructions": """
TON: Formell und professionell

STIL-VORGABEN:
- Anrede: "Sehr geehrte/r [Titel] [Name]" oder "Sehr geehrte Damen und Herren"
- Höflichkeitsform: Konsequent "Sie" (nie "Du")
- Sprache: Sachlich, klar, respektvoll
- Satzstruktur: Vollständige, korrekte Sätze
- Grussformel: "Mit freundlichen Grüssen" oder "Freundliche Grüsse"

E-MAIL-STRUKTUR:
1. Anrede (neue Zeile)
2. [Optionaler Dank/Bezug] 
3. Hauptteil: Beantwortung/Bestätigung
4. [Optional] Weitere Schritte oder Fragen
5. Grussformel (neue Zeile)

BEISPIEL-MUSTER:
---
Sehr geehrte Frau Müller,

vielen Dank für Ihre Anfrage bezüglich [Thema].

[Hauptantwort mit konkreten Informationen]

Gerne stehe ich für Rückfragen zur Verfügung.

Mit freundlichen Grüssen
---

AUFGABE: Erstelle eine formelle Antwort mit dieser Struktur.
"""
    },
    
    "friendly": {
        "name": "Freundlich",
        "icon": "😊",
        "instructions": """
TON: Freundlich und persönlich (aber professionell)

STIL-VORGABEN:
- Anrede: "Hallo [Vorname]" oder "Liebe/r [Vorname]"
- Höflichkeitsform: Entscheide basierend auf Original-E-Mail (Du/Sie)
- Sprache: Warm, zugänglich, positiv
- Satzstruktur: Natürlich, nicht zu steif
- Grussformel: "Viele Grüsse", "Beste Grüsse" oder "Liebe Grüsse"

E-MAIL-STRUKTUR:
1. Freundliche Anrede
2. Kurzer persönlicher Einstieg (Dank, positiver Bezug)
3. Hauptteil: Hilfreiche Antwort
4. [Optional] Persönliche Note oder Ausblick
5. Herzliche Grussformel

BEISPIEL-MUSTER:
---
Hallo Thomas,

vielen Dank für deine Nachricht! [Bezug auf Original]

[Hauptantwort - hilfreich und konkret]

Melde dich gerne, falls noch Fragen sind.

Viele Grüsse
---

AUFGABE: Erstelle eine freundliche, warme Antwort mit dieser Struktur.
"""
    },
    
    "brief": {
        "name": "Kurz & Knapp",
        "icon": "⚡",
        "instructions": """
TON: Kurz, präzise, effizient

STIL-VORGABEN:
- Anrede: Kurz und passend zum Kontext
- Höflichkeitsform: Wie in Original-E-Mail
- Sprache: Direkt, ohne Füllwörter
- Länge: Maximum 3-4 Sätze
- Grussformel: Kurz ("Gruss", "VG", "LG")

E-MAIL-STRUKTUR:
1. Kurze Anrede
2. Kernaussage in 1-2 Sätzen
3. [Optional] Call-to-Action
4. Kurze Grussformel

BEISPIEL-MUSTER:
---
Hallo Anna,

danke für die Info. [Kernaussage in 1 Satz]

Gruss
---

WICHTIG: Maximal 3-4 Sätze! Jedes Wort muss zählen.

AUFGABE: Erstelle eine sehr kurze, prägnante Antwort.
"""
    },
    
    "decline": {
        "name": "Höflich ablehnen",
        "icon": "🙅",
        "instructions": """
TON: Höflich ablehnend, aber konstruktiv

STIL-VORGABEN:
- Anrede: Respektvoll
- Höflichkeitsform: Sie (bei formellen Anfragen)
- Sprache: Höflich, aber bestimmt
- Struktur: Dank → Ablehnung mit Grund → Alternative (falls möglich)
- Grussformel: Professionell

E-MAIL-STRUKTUR:
1. Höfliche Anrede
2. Dank für Anfrage/Interesse
3. Höfliche Ablehnung mit knapper Begründung
4. [Optional] Alternative Vorschläge
5. Positive Grussformel

BEISPIEL-MUSTER:
---
Sehr geehrte Frau Schmidt,

vielen Dank für Ihre Anfrage bezüglich [Thema].

Leider muss ich Ihnen mitteilen, dass [Ablehnung mit Grund].

[Optional: Alternative] Falls Sie möchten, kann ich Sie aber an [Alternative] verweisen.

Ich wünsche Ihnen dennoch viel Erfolg.

Mit freundlichen Grüssen
---

WICHTIG: Höflich aber klar ablehnen, ohne Hoffnung zu machen.

AUFGABE: Erstelle eine höfliche Absage mit dieser Struktur.
"""
    }
}


# ============================================================================
# KONTEXT-BEWUSSTER PROMPT-BUILDER
# ============================================================================

def build_optimized_user_prompt(
    original_subject: str,
    original_body: str,
    original_sender: str,
    tone: str = "formal",
    thread_context: str = None,
    has_attachments: bool = False,
    attachment_names: list = None,
    language: str = "de"
) -> str:
    """
    Baut einen optimierten User-Prompt der:
    1. Email-Typ erkennt (Anfrage, Bestätigung, Frage, etc.)
    2. Kontext-relevante Hinweise gibt
    3. Klare Struktur vorgibt
    """
    
    # Tone-Instructions holen
    tone_config = TONE_PROMPTS_OPTIMIZED.get(tone, TONE_PROMPTS_OPTIMIZED["formal"])
    tone_instructions = tone_config["instructions"]
    
    # E-Mail-Typ analysieren (heuristisch)
    email_type = _detect_email_type(original_subject, original_body)
    
    # Anhang-Hinweis
    attachment_hint = ""
    if has_attachments:
        if attachment_names:
            attachment_hint = f"\n📎 ANHÄNGE: {', '.join(attachment_names)}"
        else:
            attachment_hint = "\n📎 Die Original-E-Mail enthält Anhänge"
    
    # Haupt-Prompt zusammenbauen
    prompt_parts = [
        "=" * 60,
        "ORIGINAL-E-MAIL",
        "=" * 60,
        f"Von: {original_sender or 'Unbekannt'}",
        f"Betreff: {original_subject or '(Kein Betreff)'}",
        attachment_hint,
        "",
        original_body[:2000],  # Erste 2000 Zeichen
        "",
        "=" * 60,
    ]
    
    # Thread-Context (falls vorhanden)
    if thread_context:
        prompt_parts.extend([
            "FRÜHERER E-MAIL-VERLAUF",
            "=" * 60,
            thread_context[:1000],
            "",
            "=" * 60,
        ])
    
    # E-Mail-Typ-spezifische Hinweise
    type_hint = _get_type_specific_hint(email_type)
    if type_hint:
        prompt_parts.extend([
            f"ERKANNTER E-MAIL-TYP: {email_type}",
            type_hint,
            "",
            "=" * 60,
        ])
    
    # Tone-Instructions
    prompt_parts.extend([
        "DEINE AUFGABE",
        "=" * 60,
        tone_instructions,
        "",
        "=" * 60,
        "WICHTIG - AUSGABEFORMAT",
        "=" * 60,
        "Schreibe NUR den E-Mail-Body-Text!",
        "- KEINE Betreffzeile",
        "- KEINE Meta-Informationen (Von/An/Datum)",
        "- KEINE Einleitung wie 'Hier ist die Antwort...'",
        "- Beginne DIREKT mit der Anrede",
        "",
        "STARTE JETZT MIT DER ANTWORT:"
    ])
    
    return "\n".join(prompt_parts)


def _detect_email_type(subject: str, body: str) -> str:
    """
    Erkennt E-Mail-Typ heuristisch.
    
    Returns:
        "question" | "request" | "confirmation" | "information" | "complaint" | "generic"
    """
    subject_lower = (subject or "").lower()
    body_lower = (body or "").lower()
    combined = f"{subject_lower} {body_lower}"
    
    # Frage-Indikatoren
    question_markers = ["?", "frage", "wie", "wann", "wo", "warum", "können sie", "könnten sie"]
    if any(marker in combined for marker in question_markers):
        return "question"
    
    # Anfrage-Indikatoren
    request_markers = ["anfrage", "bitte", "benötige", "brauche", "würde gerne", "könnten sie"]
    if any(marker in combined for marker in request_markers):
        return "request"
    
    # Bestätigungs-Indikatoren
    confirmation_markers = ["bestätigung", "erhalten", "angekommen", "bestätige", "danke für"]
    if any(marker in combined for marker in confirmation_markers):
        return "confirmation"
    
    # Beschwerde-Indikatoren
    complaint_markers = ["beschwerde", "problem", "fehler", "nicht funktioniert", "unzufrieden"]
    if any(marker in combined for marker in complaint_markers):
        return "complaint"
    
    # Information
    info_markers = ["mitteilen", "informieren", "bekanntgeben", "hinweis"]
    if any(marker in combined for marker in info_markers):
        return "information"
    
    return "generic"


def _get_type_specific_hint(email_type: str) -> str:
    """Gibt typ-spezifische Hinweise zurück"""
    
    hints = {
        "question": """
HINWEIS: Dies ist eine Frage-E-Mail.
→ Beantworte die gestellten Fragen konkret und vollständig
→ Strukturiere bei mehreren Fragen die Antworten klar
→ Biete bei Bedarf zusätzliche relevante Informationen an
""",
        "request": """
HINWEIS: Dies ist eine Anfrage.
→ Gehe auf die Anfrage ein (zusagen, ablehnen, oder weitere Infos einholen)
→ Sei spezifisch bei Zeitangaben und nächsten Schritten
→ Falls Ablehnung: Nenne Alternativen oder Gründe
""",
        "confirmation": """
HINWEIS: Dies ist eine Bestätigung/Eingangsbestätigung.
→ Bestätige den Erhalt ebenfalls
→ Danke für die Information
→ Gib bei Bedarf nächste Schritte an
""",
        "complaint": """
HINWEIS: Dies ist eine Beschwerde/Problemmeldung.
→ Zeige Verständnis für das Problem
→ Entschuldige dich falls angebracht
→ Biete konkrete Lösung oder nächste Schritte an
→ Bleibe professionell und lösungsorientiert
""",
        "information": """
HINWEIS: Dies ist eine Info-E-Mail.
→ Danke für die Information
→ Bestätige Kenntnisnahme
→ Falls relevant: Stelle Rückfragen oder nenne nächste Schritte
""",
        "generic": ""
    }
    
    return hints.get(email_type, "")


# ============================================================================
# FEW-SHOT EXAMPLES (Optional für schwache LLMs)
# ============================================================================

FEW_SHOT_EXAMPLES = """
BEISPIEL 1 - Frage beantworten (Formal):
---
Original: "Können wir das Meeting auf Dienstag verschieben?"

Antwort:
Sehr geehrte Frau Müller,

vielen Dank für Ihre Nachricht.

Dienstag passt mir sehr gut. Lassen Sie uns das Meeting auf Dienstag, 14:00 Uhr verlegen.

Mit freundlichen Grüssen
---

BEISPIEL 2 - Anfrage bestätigen (Freundlich):
---
Original: "Ich hätte gerne ein Angebot für..."

Antwort:
Hallo Thomas,

danke für deine Anfrage!

Ich erstelle dir gerne ein Angebot. Dazu brauche ich noch ein paar Details. Können wir kurz telefonieren? Wäre morgen um 10 Uhr möglich?

Viele Grüsse
---

BEISPIEL 3 - Kurz & Knapp:
---
Original: "Sind die Dokumente angekommen?"

Antwort:
Hi Anna,

ja, alles erhalten. Danke!

LG
---
"""


# ============================================================================
# INTEGRATION-BEISPIEL
# ============================================================================

def example_usage():
    """Zeigt wie der optimierte Prompt genutzt wird"""
    
    # Beispiel E-Mail
    original_email = {
        'subject': 'Frage zum Projekttermin',
        'body': '''Hallo Mike,
        
        können wir den Termin für das Projekt-Review auf nächste Woche 
        verschieben? Mir wäre Dienstag oder Mittwoch am liebsten.
        
        Danke und Gruss,
        Thomas''',
        'sender': 'thomas.weber@firma.de'
    }
    
    # Optimierten Prompt bauen
    optimized_prompt = build_optimized_user_prompt(
        original_subject=original_email['subject'],
        original_body=original_email['body'],
        original_sender=original_email['sender'],
        tone='friendly',
        thread_context=None,
        has_attachments=False
    )
    
    print("=" * 80)
    print("OPTIMIERTER PROMPT")
    print("=" * 80)
    print(optimized_prompt)
    print("\n" + "=" * 80)
    
    # An LLM senden
    # reply = llm.generate_text(
    #     system_prompt=REPLY_GENERATION_SYSTEM_PROMPT_OPTIMIZED,
    #     user_prompt=optimized_prompt,
    #     max_tokens=1000
    # )


# ============================================================================
# VERGLEICH: ALT vs NEU
# ============================================================================

COMPARISON = """
ALT (Generisch):
---
System: "Du bist ein E-Mail-Assistent"
User: "Erstelle eine Antwort auf diese E-Mail: [Email]"
→ LLM muss alles selbst herausfinden
→ Keine Struktur-Vorgaben
→ Oft Meta-Kommentare ("Hier ist die Antwort...")

NEU (Optimiert):
---
System: Klare Rolle + Regeln + Was zu tun/nicht zu tun
User: 
  - Strukturierte Email-Darstellung
  - E-Mail-Typ erkannt
  - Ton-spezifische Anweisungen
  - Klare Ausgabe-Format-Vorgaben
→ LLM weiß genau was zu tun ist
→ Bessere Qualität auch bei schwachen Modellen
→ Weniger Halluzinationen

ERWARTETE VERBESSERUNGEN:
✅ 40-60% bessere Antwort-Qualität
✅ Weniger "Meta-Geschwätz"
✅ Konsistentere Struktur
✅ Funktioniert besser mit schwachen LLMs (TinyLlama, Phi-3)
"""

if __name__ == "__main__":
    example_usage()
    print("\n" + COMPARISON)
