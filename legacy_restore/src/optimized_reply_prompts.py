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
- Du schreibst IMMER eine Antwort AUS SICHT DES EMPFÄNGERS der Original-E-Mail
- Du bist NICHT der Absender der Original-E-Mail, sondern derjenige der antwortet!
- Der Empfänger deiner Antwort ist der Absender der Original-E-Mail
- Die Antwort soll hilfreich, präzise und angemessen sein

WICHTIGE AUSNAHME - NEWSLETTER/MARKETING:
⛔ Bei Newsletter oder Marketing-E-Mails: Schreibe KEINE normale Antwort!
⛔ Stattdessen: "Diese E-Mail ist ein Newsletter/Marketing und erfordert keine Antwort."
⛔ Newsletter-Merkmale: Automatisch versendet, Impressum, "kann nicht abbestellt werden", "nur zum Versand"

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
❌ Gib dich NIEMALS als der Absender der Original-E-Mail aus
❌ Bei Newsletter/Marketing-Mails: Schreibe KEINE Antwort (macht keinen Sinn!)

PLATZHALTER FÜR NAMEN:
- [ABSENDER_VORNAME] = Vorname des Absenders (z.B. für "Lieber [ABSENDER_VORNAME]")
- [ABSENDER_NACHNAME] = Nachname des Absenders (z.B. für "Sehr geehrter Herr [ABSENDER_NACHNAME]")
- [ABSENDER_VOLLNAME] = Voller Name des Absenders
- [EMPFÄNGER_VORNAME] = Dein Vorname (für Unterschrift bei informellen Mails)
- [EMPFÄNGER_NACHNAME] = Dein Nachname
- [EMPFÄNGER_VOLLNAME] = Dein voller Name (für Unterschrift bei formellen Mails)

ANREDE nach Ton:
- Formell: "Sehr geehrter Herr [ABSENDER_NACHNAME]" oder "Sehr geehrte Frau [ABSENDER_NACHNAME]"
- Freundlich: "Lieber [ABSENDER_VORNAME]" oder "Liebe [ABSENDER_VORNAME]"
- Kurz: "Hallo [ABSENDER_VORNAME]"

GRUSS nach Ton:
- Formell: Unterschrift mit [EMPFÄNGER_VOLLNAME]
- Freundlich/Kurz: Unterschrift nur mit [EMPFÄNGER_VORNAME]
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
- Anrede: "Liebe [Vorname]" oder "Lieber [Vorname]" (Uni-Jargon - NICHT "Hallo"!)
- Höflichkeitsform: Entscheide basierend auf Original-E-Mail (Du/Sie)
- Sprache: Warm, zugänglich, positiv
- Satzstruktur: Natürlich, nicht zu steif
- Grussformel: "Viele Grüsse", "Beste Grüsse" oder "Liebe Grüsse"

E-MAIL-STRUKTUR:
1. Freundliche Anrede (IMMER "Liebe/r" verwenden!)
2. Kurzer persönlicher Einstieg (Dank, positiver Bezug)
3. Hauptteil: Hilfreiche Antwort
4. [Optional] Persönliche Note oder Ausblick
5. Herzliche Grussformel

BEISPIEL-MUSTER:
---
Lieber Thomas,

vielen Dank für deine Nachricht! [Bezug auf Original]

[Hauptantwort - hilfreich und konkret]

Melde dich gerne, falls noch Fragen sind.

Viele Grüsse
---

AUFGABE: Erstelle eine freundliche, warme Antwort mit dieser Struktur und verwende IMMER "Liebe/r" in der Anrede.
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
        "newsletter" | "question" | "request" | "confirmation" | "information" | "complaint" | "generic"
    """
    subject_lower = (subject or "").lower()
    body_lower = (body or "").lower()
    combined = f"{subject_lower} {body_lower}"
    
    # Newsletter/Marketing-Indikatoren (HÖCHSTE PRIORITÄT - keine Antwort nötig!)
    newsletter_markers = [
        "newsletter", "abbestellen", "unsubscribe", "update für sie",
        "viel spass beim lesen", "marketing", "promotional", 
        "diese e-mail wurde automatisch", "automatisch versendete nachricht",
        "antwort auf diese e-mail ist nicht möglich", "nur zum nachrichtenversand",
        "fester leistungsbestandteil", "kann nicht abbestellt werden",
        "impressum", "ust-id"
    ]
    # Prüfe auf Newsletter (mind. 2 Marker für höhere Genauigkeit)
    newsletter_count = sum(1 for marker in newsletter_markers if marker in combined)
    if newsletter_count >= 2:
        return "newsletter"
    
    # Beschwerde-Indikatoren (ZUERST prüfen - höchste Priorität)
    complaint_markers = ["beschwerde", "problem", "fehler", "nicht funktioniert", "unzufrieden", "reklamation", "defekt"]
    if any(marker in combined for marker in complaint_markers):
        return "complaint"
    
    # Frage-Indikatoren
    question_markers = ["?", "frage", "wie", "wann", "wo", "warum", "können sie", "könnten sie"]
    if any(marker in combined for marker in question_markers):
        return "question"
    
    # Anfrage-Indikatoren
    request_markers = ["anfrage", "bitte", "benötige", "brauche", "würde gerne", "könnte ich"]
    if any(marker in combined for marker in request_markers):
        return "request"
    
    # Bestätigungs-Indikatoren
    confirmation_markers = ["bestätigung", "erhalten", "angekommen", "bestätige", "danke für"]
    if any(marker in combined for marker in confirmation_markers):
        return "confirmation"
    
    # Information
    info_markers = ["mitteilen", "informieren", "bekanntgeben", "hinweis"]
    if any(marker in combined for marker in info_markers):
        return "information"
    
    return "generic"


def _get_type_specific_hint(email_type: str) -> str:
    """Gibt typ-spezifische Hinweise zurück"""
    
    hints = {
        "newsletter": """
⛔⛔⛔ STOP - DIES IST EIN NEWSLETTER ⛔⛔⛔

Dies ist ein Newsletter oder eine automatisierte Marketing-E-Mail!

❌ Schreibe KEINE normale Antwort!
❌ Der Empfänger erwartet KEINE Antwort!

Stattdessen:
→ Schreibe nur: "Diese E-Mail ist ein Newsletter und erfordert keine Antwort."
→ KEINE Anrede, KEINE Grussformel, KEIN normaler Brief-Stil!
→ Nur dieser eine Satz!
""",
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
