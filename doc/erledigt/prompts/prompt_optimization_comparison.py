"""
PROMPT-OPTIMIERUNG: VORHER/NACHHER VERGLEICH
=============================================

Dieser Guide zeigt die konkreten Verbesserungen durch optimierte Prompts
"""

# ============================================================================
# BEISPIEL 1: Anfrage-E-Mail
# ============================================================================

EXAMPLE_1_INPUT = """
Von: anna.mueller@firma.de
Betreff: Angebot für KI-Integration

Guten Tag Herr Schmidt,

vielen Dank für das interessante Gespräch letzte Woche. 
Können Sie mir ein Angebot für die KI-Integration zusenden?

Mit freundlichen Grüßen,
Anna Müller
"""

# --- VORHER: Generischer Prompt ---

EXAMPLE_1_OLD_PROMPT = """
Erstelle eine Antwort auf diese E-Mail:

[Email-Inhalt]

Schreibe eine passende Antwort.
"""

EXAMPLE_1_OLD_OUTPUT = """
Hallo!

Vielen Dank für Ihre E-Mail. Gerne sende ich Ihnen ein Angebot zu.
Ich werde mich darum kümmern und melde mich bald bei Ihnen.

Haben Sie noch weitere Fragen?

Mit freundlichen Grüßen
"""

# PROBLEME:
# ❌ "Hallo!" zu informell für formelle Anfrage
# ❌ "melde mich bald" - vage, keine konkreten Zeitangaben
# ❌ "Haben Sie noch weitere Fragen?" - unnötig
# ❌ Keine klare Struktur


# --- NACHHER: Optimierter Prompt ---

EXAMPLE_1_NEW_PROMPT = """
============================================================
ORIGINAL-E-MAIL
============================================================
Von: anna.mueller@firma.de
Betreff: Angebot für KI-Integration

[Email-Inhalt]

============================================================
ERKANNTER E-MAIL-TYP: request

HINWEIS: Dies ist eine Anfrage.
→ Gehe auf die Anfrage ein (zusagen, ablehnen, oder weitere Infos einholen)
→ Sei spezifisch bei Zeitangaben und nächsten Schritten
→ Falls Ablehnung: Nenne Alternativen oder Gründe

============================================================
DEINE AUFGABE
============================================================

TON: Formell und professionell

STIL-VORGABEN:
- Anrede: "Sehr geehrte/r [Titel] [Name]"
- Höflichkeitsform: Konsequent "Sie"
- Sprache: Sachlich, klar, respektvoll
- Grussformel: "Mit freundlichen Grüssen"

E-MAIL-STRUKTUR:
1. Formelle Anrede
2. Dank für Anfrage
3. Konkrete Zusage/Information
4. Nächste Schritte
5. Grussformel

WICHTIG - AUSGABEFORMAT:
Schreibe NUR den E-Mail-Body-Text!
- KEINE Betreffzeile
- KEINE Meta-Informationen
- Beginne DIREKT mit der Anrede
"""

EXAMPLE_1_NEW_OUTPUT = """
Sehr geehrte Frau Müller,

vielen Dank für Ihre Anfrage bezüglich der KI-Integration.

Gerne erstelle ich Ihnen ein detailliertes Angebot. Ich werde Ihnen 
dieses bis spätestens Freitag, den 10. Januar zusenden.

Sollten Sie vorab noch Fragen haben, stehe ich Ihnen jederzeit 
gerne zur Verfügung.

Mit freundlichen Grüssen
"""

# VERBESSERT:
# ✅ Korrekte formelle Anrede ("Sehr geehrte Frau Müller")
# ✅ Konkreter Zeitrahmen ("bis spätestens Freitag, 10. Januar")
# ✅ Professioneller Ton durchgehend
# ✅ Klare Struktur


# ============================================================================
# BEISPIEL 2: GMX Newsletter (Problem-Fall)
# ============================================================================

EXAMPLE_2_INPUT = """
Von: newsletter@gmx.net
Betreff: Spiel Spaß mit dem Moorhuhn

Hallo Frau Weber, diese Woche für Sie: Spiel Spaß mit dem Moorhuhn, 
Casino Jackpot Gewinn...
[Newsletter-Spam]
"""

# --- VORHER: Kein Pre-Filter, schwacher Prompt ---

EXAMPLE_2_OLD_OUTPUT = """
Sehr geehrte/r Frau Weber,

vielen Dank für Ihre Einladung zum GMX Magazin. Wir freuen uns darauf, 
dass Sie unsere Woche für Sie haben, um sich über unsere aktuellen Spiele 
und Angebote zu informieren.

Dieses Mal ist unser Fokus auf Super Duper Moorhuhn, das Online Casino 
Game mit Kultfaktor...

Mit freundlichen Grüßen,
Der GMX Magazin-Team
"""

# PROBLEME:
# ❌ LLM antwortet auf Newsletter (macht keinen Sinn)
# ❌ "sich selbst" als GMX-Team antworten
# ❌ Wiederholt Newsletter-Inhalt
# ❌ Kompletter Unsinn


# --- NACHHER: Mit Pre-Filter + optimiertem Prompt ---

EXAMPLE_2_NEW_OUTPUT = """
⛔ KEINE ANTWORT GENERIERT

Grund: E-Mail zu unwichtig (Importance: 3/10)
Filter: importance_filter
Confidence: 95%

Suggestion: Für diese E-Mail wird kein Antwort-Entwurf empfohlen
"""

# VERBESSERT:
# ✅ Pre-Filter verhindert LLM-Aufruf komplett
# ✅ Keine unsinnige Antwort
# ✅ User bekommt sinnvolle Erklärung
# ✅ 2-3 Minuten CPU-Zeit gespart


# ============================================================================
# BEISPIEL 3: Kurze Kollegen-Frage
# ============================================================================

EXAMPLE_3_INPUT = """
Von: thomas@firma.de
Betreff: Re: Meeting

Hi Mike,

können wir auf 15 Uhr verschieben?

LG Thomas
"""

# --- VORHER: Generischer Prompt ---

EXAMPLE_3_OLD_OUTPUT = """
Hallo Thomas,

vielen Dank für Ihre Nachricht bezüglich des Meetings.

Ja, eine Verschiebung auf 15 Uhr ist möglich. Ich werde den 
Termin entsprechend anpassen und Ihnen eine Bestätigung zusenden.

Sollten Sie weitere Fragen haben, stehe ich Ihnen gerne zur Verfügung.

Mit freundlichen Grüßen,
Mike
"""

# PROBLEME:
# ❌ Viel zu formell für lockere Kollegen-Mail
# ❌ "Ihre Nachricht" statt "deine Nachricht" (falsches Sie/Du)
# ❌ Viel zu lang für simple Ja/Nein-Frage
# ❌ Unnötige Floskeln


# --- NACHHER: Ton "brief" mit Optimierung ---

EXAMPLE_3_NEW_OUTPUT = """
Hi Thomas,

klar, 15 Uhr passt!

Gruss,
Mike
"""

# VERBESSERT:
# ✅ Kurz und prägnant (wie Anfrage)
# ✅ Richtiges "Du"
# ✅ Passt zum Ton der Anfrage
# ✅ Keine unnötigen Floskeln


# ============================================================================
# BEISPIEL 4: Beschwerde-E-Mail
# ============================================================================

EXAMPLE_4_INPUT = """
Von: kunde@example.com
Betreff: Problem mit Lieferung

Sehr geehrter Herr Schmidt,

ich bin sehr unzufrieden. Die Lieferung ist nicht angekommen 
und niemand hat sich bei mir gemeldet!

Mit freundlichen Grüßen,
Max Mustermann
"""

# --- VORHER: Generischer Prompt ---

EXAMPLE_4_OLD_OUTPUT = """
Sehr geehrter Herr Mustermann,

vielen Dank für Ihre Nachricht.

Es tut mir leid zu hören, dass Sie Probleme mit der Lieferung haben.
Ich werde mich darum kümmern.

Mit freundlichen Grüßen
"""

# PROBLEME:
# ❌ Zu generisch, keine konkrete Lösung
# ❌ Keine Entschuldigung
# ❌ "werde mich kümmern" - vage
# ❌ Keine nächsten Schritte


# --- NACHHER: E-Mail-Typ "complaint" erkannt ---

EXAMPLE_4_NEW_OUTPUT = """
Sehr geehrter Herr Mustermann,

vielen Dank für Ihre Nachricht und bitte entschuldigen Sie die 
Unannehmlichkeiten.

Ich habe Ihr Anliegen sofort an unsere Logistik-Abteilung weitergeleitet. 
Sie werden sich innerhalb der nächsten 24 Stunden bei Ihnen melden, um 
das Problem zu klären und eine Lösung zu finden.

Falls Sie in der Zwischenzeit weitere Fragen haben, erreichen Sie mich 
unter dieser E-Mail-Adresse oder telefonisch unter [Telefonnummer].

Nochmals vielen Dank für Ihre Geduld.

Mit freundlichen Grüßen
"""

# VERBESSERT:
# ✅ Klare Entschuldigung
# ✅ Konkrete Zeitangabe ("innerhalb 24 Stunden")
# ✅ Nächste Schritte genannt
# ✅ Alternative Kontaktmöglichkeit angeboten
# ✅ Professionell aber empathisch


# ============================================================================
# ZUSAMMENFASSUNG DER VERBESSERUNGEN
# ============================================================================

IMPROVEMENTS_SUMMARY = """
============================================================
ZUSAMMENFASSUNG: PROMPT-OPTIMIERUNG BRINGT
============================================================

1. 📊 BESSERE QUALITÄT
   - Passender Ton (formal/freundlich/kurz)
   - Korrekte Anrede (Sie/Du basierend auf Context)
   - Strukturierte Antworten (Anrede → Inhalt → Gruss)
   
2. 🎯 KONTEXT-BEWUSST
   - E-Mail-Typ erkannt (Frage/Anfrage/Beschwerde)
   - Typ-spezifische Anweisungen
   - Bessere Bezugnahme auf Original
   
3. 🚫 WENIGER FEHLER
   - Keine Meta-Kommentare ("Hier ist die Antwort...")
   - Keine Betreffzeilen im Body
   - Keine unnötigen Floskeln
   
4. ⚡ MIT PRE-FILTER
   - Newsletter/Spam werden VOR LLM gefiltert
   - Keine unsinnigen Antworten mehr
   - 60-90% weniger LLM-Aufrufe
   
5. 🤖 FUNKTIONIERT MIT SCHWACHEN LLMs
   - Klare Anweisungen → bessere Results
   - Auch TinyLlama & Phi-3 profitieren
   - Strukturierte Prompts kompensieren Modell-Schwäche

============================================================
ERWARTETE METRIKEN
============================================================

Ohne Optimierung:
- Qualität: 40-60% gut (viele Fehler)
- Ton-Passung: 30-50% (oft falsch)
- Meta-Kommentare: 30-40% der Antworten
- Newsletter-Antworten: Ja (unsinnig)

Mit Optimierung + Pre-Filter:
- Qualität: 75-90% gut
- Ton-Passung: 80-95% korrekt
- Meta-Kommentare: < 5%
- Newsletter-Antworten: Nein (gefiltert)

ZEITERSPARNIS:
- Pre-Filter: 60-90% weniger LLM-Calls
- Bessere Prompts: 20-30% kürzere Generation
- Gesamt: 70-95% Zeit gespart!

============================================================
NÄCHSTE SCHRITTE
============================================================

1. ✅ Pre-Filter installieren (siehe INSTALLATION_ANLEITUNG.md)
2. ✅ Optimierte Prompts einbauen (siehe Integration-Guide)
3. ⏳ Mit echten E-Mails testen
4. ⏳ Thresholds & Keywords anpassen
5. ⏳ Few-Shot Learning implementieren (Phase 2)

Pro-Tipp:
Starte mit Pre-Filter (größter Hebel) und optimiere dann 
Schritt für Schritt die Prompts basierend auf echten Beispielen.
"""

if __name__ == "__main__":
    print("=" * 70)
    print("PROMPT-OPTIMIERUNG: VORHER/NACHHER")
    print("=" * 70)
    print()
    
    print("📧 BEISPIEL 1: Formelle Anfrage")
    print("-" * 70)
    print("VORHER:")
    print(EXAMPLE_1_OLD_OUTPUT)
    print("\nNACHHER:")
    print(EXAMPLE_1_NEW_OUTPUT)
    print()
    
    print("📧 BEISPIEL 2: GMX Newsletter (Problem)")
    print("-" * 70)
    print("VORHER:")
    print(EXAMPLE_2_OLD_OUTPUT)
    print("\nNACHHER:")
    print(EXAMPLE_2_NEW_OUTPUT)
    print()
    
    print("📧 BEISPIEL 3: Kurze Kollegen-Mail")
    print("-" * 70)
    print("VORHER:")
    print(EXAMPLE_3_OLD_OUTPUT)
    print("\nNACHHER:")
    print(EXAMPLE_3_NEW_OUTPUT)
    print()
    
    print(IMPROVEMENTS_SUMMARY)
