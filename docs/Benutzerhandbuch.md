# Benutzerhandbuch - KI-Mail-Helper

**Version:** 1.4.0  
**Stand:** 09.01.2026  

---

## Inhaltsverzeichnis

1. [Übersicht](#übersicht)
2. [Installation & Setup](#installation--setup)
3. [Email-Accounts einrichten](#email-accounts-einrichten)
4. [Dashboard & 3×3 Matrix](#dashboard--3×3-matrix)
5. [KI-gestützte Priorisierung](#ki-gestützte-priorisierung)
6. [Email-Anonymisierung](#email-anonymisierung)
7. [Reply Generator](#reply-generator)
8. [Auto-Rules](#auto-rules)
9. [Tag-System](#tag-system)
10. [Whitelist & UrgencyBooster](#whitelist--urgencybooster)
11. [Semantic Search](#semantic-search)
12. [Erweiterte Einstellungen](#erweiterte-einstellungen)

---

## Übersicht

**KI-Mail-Helper** ist ein selbst-gehosteter Email-Assistent mit Zero-Knowledge-Verschlüsselung. Der Server sieht niemals deine Klartext-Emails – alle sensiblen Daten werden im Browser mit deinem Master-Passwort verschlüsselt.

### Kernfeatures

- **🔐 Zero-Knowledge:** AES-256-GCM Verschlüsselung, DEK/KEK-Pattern
- **🎯 3×3 Prioritäts-Matrix:** Dringlichkeit × Wichtigkeit mit Farbcodierung
- **🤖 KI-Analyse:** Automatische Priorisierung mit spaCy NLP + Ensemble Learning
- **🛡️ Email-Anonymisierung:** PII-Entfernung vor Cloud-AI-Übertragung (DSGVO)
- **✍️ Reply Generator:** 4 Ton-Varianten mit optimierten Prompts für Small LLMs
- **⚙️ Auto-Rules:** 14 Bedingungen für automatische Aktionen
- **🏷️ Smart Tags:** KI-Vorschläge + Learning-System
- **🔍 Semantic Search:** Vector-basierte Suche mit Embeddings
- **📤 SMTP-Versand:** Antworten & neue Emails mit Sent-Sync

---

## Installation & Setup

### Voraussetzungen

```bash
# System-Requirements
- Python 3.9+
- pip
- virtualenv (empfohlen)
- Git

# Optional: spaCy Modell für NLP
python -m spacy download de_core_news_sm
```

### Installation

```bash
# 1. Repository klonen
git clone https://github.com/yourusername/KI-Mail-Helper.git
cd KI-Mail-Helper

# 2. Virtual Environment erstellen
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# 3. Dependencies installieren
pip install -r requirements.txt

# 4. Datenbank initialisieren
flask db upgrade

# 5. Server starten
python src/01_web_app.py
```

### Erster Start

1. Browser öffnen: `http://localhost:5001`
2. Registrieren: Benutzername + Master-Passwort wählen
3. **⚠️ Master-Passwort sicher aufbewahren** – ohne Passwort sind Emails nicht entschlüsselbar!
4. Login und Email-Account hinzufügen

---

## Email-Accounts einrichten

### IMAP-Account (GMX, Posteo, etc.)

1. Gehe zu **Settings → Email Accounts → Add Account**
2. Wähle **IMAP**
3. Gib ein:
   - **Email:** deine@email.de
   - **IMAP Server:** imap.gmx.net (Beispiel GMX)
   - **IMAP Port:** 993 (SSL)
   - **IMAP Username:** deine@email.de
   - **IMAP Password:** dein-passwort
   - **SMTP Server:** mail.gmx.net
   - **SMTP Port:** 465 (SSL)
4. Klicke **Add Account**

### Gmail OAuth

1. Gehe zu **Settings → Email Accounts → Add Account**
2. Wähle **Gmail OAuth**
3. Klicke **Authenticate with Gmail**
4. Folge dem OAuth-Flow (Google-Login)
5. Erlaube Zugriff auf Email-Postfach

### Fetch-Filter (Optional)

Unter **Settings → Email Accounts → Edit** kannst du pro Account festlegen:

- **Ordner:** Nur bestimmte IMAP-Ordner abrufen (z.B. INBOX, Sent)
- **Datum:** Nur Emails ab bestimmtem Datum
- **UNSEEN:** Nur ungelesene Emails
- **Enable AI Analysis:** KI-Analyse beim Fetch aktivieren
- **Enable UrgencyBooster:** Urgency-Override für Trusted Senders

---

## Dashboard & 3×3 Matrix

### Prioritäts-Matrix

Die **3×3 Matrix** organisiert Emails nach **Dringlichkeit** (Urgency) und **Wichtigkeit** (Importance):

```
          Wichtigkeit →
       Niedrig  Mittel  Hoch
D  H │   3       2      1
r  O │   6       5      4
i  C │   9       8      7
n  H │
g
l
i
c
h
k
e
i
t
↓
```

**Farbcodierung:**
- 🔴 **Rot (1):** Sehr dringend & sehr wichtig → sofort bearbeiten
- 🟠 **Orange (2-4):** Hohe Priorität
- 🟡 **Gelb (5-6):** Mittlere Priorität
- 🟢 **Grün (7-9):** Niedrige Priorität

### Navigation

- **Klick auf Zelle:** Zeigt Emails in dieser Priorität
- **Account-Filter:** Dropdown oben rechts (z.B. "Work", "Private")
- **UNSEEN Badge:** Zeigt Anzahl ungelesener Emails

---

## KI-gestützte Priorisierung

Die KI analysiert jede Email automatisch und schlägt eine Priorität vor:

### Funktionsweise

1. **spaCy NLP (80% Gewicht):**
   - Named Entity Recognition (NER): Personen, Orte, Organisationen
   - Linguistic Features: POS-Tags, Dependency Parsing
   - Email-spezifische Muster: Betreff-Keywords, Absender-Domain

2. **Keyword-Matching (20% Gewicht):**
   - Dringlichkeits-Keywords: "dringend", "asap", "urgent", "deadline"
   - Wichtigkeits-Keywords: "wichtig", "kritisch", "critical", "VIP"

3. **Ensemble Learning:**
   - 4 SGD-Classifier: Urgency, Importance, Spam, Kategorie
   - Incremental Learning: Lernt aus deinen Korrekturen
   - Confidence Tracking: `ai_confidence` zeigt Vorhersage-Qualität (0.0-1.0)

### KI-Vorhersage nutzen

1. Email öffnen → siehe **AI Prediction** Badge:
   - **Confidence:** 85% → Hohe Sicherheit der Vorhersage
   - **Predicted Priority:** 2 (Orange)
   - **User-Set Priority:** (leer, wenn noch nicht gesetzt)

2. **Übernehmen:** Klicke auf Badge → Priorität wird übernommen
3. **Korrigieren:** Wähle andere Priorität → System lernt aus Feedback

### Confidence Tracking

- **0.0-0.6:** Niedrig → System unsicher, manuelle Prüfung empfohlen
- **0.6-0.8:** Mittel → Akzeptable Vorhersage
- **0.8-1.0:** Hoch → Hohe Sicherheit

---

## Email-Anonymisierung

**Phase 22** entfernt personenbezogene Daten (PII) vor Cloud-AI-Übertragung:

### 3 Anonymisierungs-Stufen

1. **Level 1 – Regex:**
   - Ersetzt: Emails, Telefon, IBAN, URLs
   - Performance: ~3-5ms
   - Beispiel: `max@example.com` → `[EMAIL]`

2. **Level 2 – spaCy Light:**
   - Regex + Personen (PER)
   - Performance: ~10-20ms
   - Beispiel: `Max BEISPIEL` → `[PERSON]`

3. **Level 3 – spaCy Full:**
   - Regex + PER + ORG + GPE + LOC
   - Performance: ~10-15ms
   - Beispiel: `Siemens AG in Berlin` → `[ORGANIZATION] in [LOCATION]`

### Verwendung

**Automatisch beim Fetch:**
- Aktiviere unter **Settings → Email Accounts → Enable AI Analysis**
- Beim Abrufen werden Emails automatisch anonymisiert (Level 3)

**On-the-fly beim Reply:**
- Wenn keine anonymisierte Version existiert, wird beim Reply-Generieren automatisch anonymisiert
- Anonymisierte Version wird in DB gespeichert für zukünftige Verwendung

**Manuell in Email-Detail:**
- Toggle **Anonymize** im Reply-Modal
- Bei Cloud-Provider (OpenAI, Anthropic) automatisch aktiviert

---

## Reply Generator

Generiere KI-Antworten in **4 Ton-Varianten** mit optimierten Prompts für Small LLMs:

### Ton-Stile

1. **Formal:**
   - Höflich, professionell, distanziert
   - Für: Geschäftspartner, Behörden, unbekannte Kontakte

2. **Freundlich:**
   - Warm, persönlich, sympathisch
   - Für: Kollegen, Bekannte, langjährige Kontakte

3. **Direkt:**
   - Klar, knapp, sachlich
   - Für: Schnelle Rückfragen, interne Kommunikation

4. **Neutral:**
   - Ausgewogen, höflich-sachlich
   - Für: Standardfälle, neutrale Kontakte

### Reply generieren

1. Email öffnen → Klick **Reply** Button
2. **Reply Modal öffnet sich:**
   - **Provider:** Ollama, OpenAI, Anthropic, Mistral
   - **Model:** Abhängig von Provider (z.B. llama3.2:3b, gpt-4o)
   - **Tone:** Formal, Freundlich, Direkt, Neutral
   - **Anonymize:** Toggle für PII-Entfernung
3. Klick **Generieren** → KI erstellt Draft
4. **Draft bearbeiten** im Editor
5. **Senden** oder **Verwerfen**

### Provider/Model Selection

**Ollama (Lokal):**
- Modelle: llama3.2:3b, mistral:7b, qwen2.5:3b, etc.
- Keine Kosten, keine Internetverbindung nötig
- Empfohlen für: Privacy-Anforderungen, häufige Nutzung

**OpenAI (Cloud):**
- Modelle: gpt-4o, gpt-4o-mini, gpt-3.5-turbo
- Temperatur: Nicht unterstützt für o1/o3/gpt-5
- Empfohlen für: Höchste Qualität

**Anthropic (Cloud):**
- Modelle: claude-3-5-sonnet, claude-3-5-haiku
- Empfohlen für: Lange Kontext-Fenster

**Mistral (Cloud):**
- Modelle: mistral-large-latest, mistral-small-latest
- Empfohlen für: Europäische Datensouveränität

### Account-Specific Signatures

Unter **Settings → Reply Styles** kannst du pro Account Signaturen festlegen:

```
Best regards,
Max Mustermann
Senior Project Manager
Firma GmbH
+49 30 12345678
max.mustermann@firma.de
```

Im Reply-Modal wird die passende Signatur automatisch eingefügt.

---

## Auto-Rules

Automatisiere Aktionen mit **14 Bedingungen:**

### Bedingungen

- **Sender:** Von bestimmter Email-Adresse
- **Sender Domain:** z.B. @firma.de
- **Subject Contains:** Betreff enthält Keyword
- **Body Contains:** Text enthält Keyword
- **Has Attachment:** Email hat Anhang
- **Attachment Type:** z.B. .pdf, .xlsx
- **Priority:** Bestimmte Matrix-Position
- **AI Confidence:** z.B. > 0.8
- **Account:** Bestimmter Email-Account
- **Tag:** Bestimmtes Tag
- **Is Unread:** Ungelesen
- **Received After:** Datum
- **Received Before:** Datum
- **Thread Count:** Anzahl Emails im Thread

### Aktionen

- **Set Priority:** Priorität setzen
- **Add Tag:** Tag hinzufügen
- **Mark as Read/Unread**
- **Move to Folder**
- **Generate Reply:** Automatische Antwort-Generierung
- **Send Notification:** Email/Push-Benachrichtigung

### Beispiel: Newsletter Auto-Tag

```yaml
Bedingung:
  - Sender Domain: @newsletter.com
  - Has Attachment: False

Aktion:
  - Add Tag: "Newsletter"
  - Set Priority: 9 (niedrig)
```

---

## Tag-System

### Manuelle Tags

1. Email öffnen → **Tags** Button
2. Bestehende Tags auswählen oder neues Tag erstellen
3. Multi-Tag-Auswahl möglich

### KI-Vorschläge

Die KI schlägt Tags basierend auf:
- **Content:** Email-Inhalt + Betreff
- **Learning:** Bisherige Tag-Zuweisungen
- **Pattern:** Ähnliche Emails mit gleichen Tags

### Feedback-System

- **✅ Accept:** Tag übernehmen → System lernt (positives Feedback)
- **❌ Reject:** Tag ablehnen → System lernt (negatives Feedback)

### Tag-Filter im Dashboard

Klick auf Tag-Badge → Zeigt alle Emails mit diesem Tag

---

## Whitelist & UrgencyBooster

### Trusted Senders

Definiere Absender, deren Emails **immer** als dringend eingestuft werden:

1. Gehe zu **Whitelist** Seite (`/whitelist`)
2. **Global Whitelist:**
   - Gilt für alle Email-Accounts
   - Beispiel: CEO, wichtige Kunden

3. **Account-Specific Whitelist:**
   - Nur für bestimmten Account
   - Beispiel: Team-Lead im Work-Account

### UrgencyBooster

- **Override:** Setzt Urgency automatisch auf "High" (auch wenn KI niedrig vorschlägt)
- **Account-Level Toggle:** Aktiviere/Deaktiviere pro Account unter **Settings → Email Accounts**

### Batch-Operationen

- **Bulk Delete:** Mehrere Einträge auf einmal löschen
- **Live-Filter:** Suche in Whitelist nach Email/Account

---

## Semantic Search

Finde Emails basierend auf **semantischer Ähnlichkeit** statt nur Keywords:

### Verwendung

1. Gehe zu **Search** Seite
2. Gib Suchanfrage ein:
   - **Keyword:** "Rechnung" → Findet auch "Invoice", "Faktura"
   - **Concept:** "Projektabschluss" → Findet Emails über Projekt-Ende
   - **Question:** "Wann ist das Meeting?" → Findet Terminanfragen

3. **Ergebnis:**
   - Emails mit semantischem Match (nicht nur exakte Wörter)
   - Similarity Score (0.0-1.0)

### Embedding-Modelle

Unter **Settings → AI Settings** wähle Embedding-Provider:
- **OpenAI:** text-embedding-3-small (beste Qualität)
- **Mistral:** mistral-embed
- **Ollama:** nomic-embed-text (lokal)

---

## Erweiterte Einstellungen

### Zero-Knowledge Verschlüsselung

- **Master-Key:** Nur im Browser-RAM, niemals auf Server
- **DEK (Data Encryption Key):** Verschlüsselt Emails (AES-256-GCM)
- **KEK (Key Encryption Key):** Verschlüsselt DEK mit Master-Key
- **Session-basiert:** Nach Logout wird Master-Key gelöscht

### Datenspeicherung

- **Datenbank:** SQLite (Standard) oder PostgreSQL (Production)
- **Verschlüsselt:** Subject, Body, Anhänge
- **Klartext:** Absender, Empfänger, Datum (für Suche/Filter)

### Performance-Tipps

1. **Fetch-Filter verwenden:** Nur relevante Ordner/Zeiträume abrufen
2. **AI-Analyse deaktivieren:** Für unwichtige Accounts (Newsletter)
3. **Batch-Fetch:** Mehrere Accounts gleichzeitig abrufen
4. **Cleanup:** Alte Emails regelmäßig archivieren/löschen

### Backup & Migration

```bash
# Datenbank-Backup
sqlite3 your_database.db ".backup backup.db"

# Migration zu PostgreSQL
flask db migrate -m "migration description"
flask db upgrade
```

---

## Troubleshooting

### Email-Fetch funktioniert nicht

- **IMAP-Credentials prüfen:** Settings → Email Accounts → Edit
- **IMAP-Port korrekt:** 993 (SSL) oder 143 (STARTTLS)
- **App-Password:** Gmail/Outlook benötigen App-spezifisches Passwort
- **Logs prüfen:** `/logs/app.log`

### KI-Analyse liefert schlechte Ergebnisse

- **Confidence niedrig:** System braucht mehr Training-Daten
- **Feedback geben:** Prioritäten korrigieren → System lernt
- **spaCy-Modell:** Prüfe ob `de_core_news_sm` installiert ist

### Reply-Generator startet nicht

- **Provider prüfen:** Settings → AI Settings → Check API-Key
- **Model verfügbar:** Ollama-Modell gedownloadet?
- **Anonymisierung:** Toggle deaktivieren wenn nicht benötigt

### Whitelist funktioniert nicht

- **UrgencyBooster aktiviert:** Settings → Email Accounts → Enable UrgencyBooster
- **Richtige Email:** Exakte Email-Adresse in Whitelist
- **Account-Mapping:** Bei Account-Specific Whitelist: korrekten Account gewählt?

---

## Support & Community

- **GitHub:** https://github.com/yourusername/KI-Mail-Helper
- **Issues:** Bug-Reports & Feature-Requests
- **Wiki:** Erweiterte Dokumentation
- **Discussions:** Community-Forum

---

**Viel Erfolg mit KI-Mail-Helper! 🚀**
