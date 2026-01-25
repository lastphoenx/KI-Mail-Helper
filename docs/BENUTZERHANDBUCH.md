# 📧 KI-Mail-Helper – Benutzerhandbuch

**Version:** 2.2.2 (Multi-User Edition)  
**Stand:** Januar 2026

---

## Inhaltsverzeichnis

1. [Einführung](#1-einführung)
2. [Erste Schritte](#2-erste-schritte)
3. [Das Dashboard](#3-das-dashboard)
4. [Email-Liste & Suche](#4-email-liste--suche)
5. [Email-Detailansicht](#5-email-detailansicht)
6. [Tag-Verwaltung](#6-tag-verwaltung)
7. [Auto-Rules](#7-auto-rules)
8. [Antwort-Stile](#8-antwort-stile)
9. [KI-Priorisierung](#9-ki-priorisierung)
10. [Mail-Verarbeitung & Status](#10-mail-verarbeitung--status)
11. [KI-Übersetzer](#11-ki-übersetzer)
12. [Ordner-Audit](#12-ordner-audit)
13. [Einstellungen](#13-einstellungen)
14. [Sicherheit & Datenschutz](#14-sicherheit--datenschutz)
15. [Fehlerbehebung](#15-fehlerbehebung)

---

## 1. Einführung

KI-Mail-Helper ist ein selbst-gehosteter Email-Organizer mit Multi-User-Support, der künstliche Intelligenz nutzt, um deine Emails automatisch zu analysieren, zu priorisieren und zu beantworten.

### Kernfunktionen

| Feature | Beschreibung |
|---------|--------------|
| **🎯 3×3 Prioritäts-Matrix** | Automatische Bewertung nach Dringlichkeit × Wichtigkeit |
| **🧠 KI-Priorisierung** | spaCy NLP (80%) + Keywords (20%) + Ensemble Learning |
| **🎓 Personal Classifier** | Individuelles ML-Modell aus deinen Korrekturen |
| **🛡️ Email-Anonymisierung** | spaCy PII-Entfernung vor Cloud-AI (DSGVO-konform) |
| **🔍 Semantische Suche** | Finde Emails nach Bedeutung, nicht nur Keywords |
| **✉️ KI-Antworten + Versand** | Generierte Antwort-Entwürfe direkt per SMTP senden |
| **⚡ Auto-Rules Engine** | Automatische Aktionen basierend auf Regeln |
| **🏷️ Intelligente Tags** | KI schlägt Tags vor, lernt aus deinem Verhalten |
| **📁 IMAP-Aktionen** | Löschen, Verschieben, Flaggen direkt aus der App |
| **🔐 Zero-Knowledge** | Server sieht niemals Klartext-Daten |
| **👥 Multi-User** | Mehrere Benutzer mit isolierten Daten |

### Was diese App NICHT ist

- Kein vollwertiger Email-Client (aber Antworten senden geht!)
- Kein Spam-Filter (das macht dein Email-Provider)
- Keine Cloud-Lösung (läuft auf deinem eigenen Server)

---

## 2. Erste Schritte

### 2.1 Registrierung

1. Öffne die App im Browser: `https://dein-server:5000`
2. Klicke auf **"Registrieren"**
3. Fülle das Formular aus:
   - **Benutzername:** 3-80 Zeichen
   - **E-Mail:** Deine Email-Adresse
   - **Passwort:** Mindestens 24 Zeichen

> ⚠️ **Wichtig:** Das Passwort ist dein **Master-Passwort**. Es verschlüsselt alle deine Daten. Bei Verlust sind deine Daten **unwiederbringlich verloren**!

> **ℹ️ Hinweis:** Der **erste User kann sich frei registrieren**. Alle weiteren User benötigen einen Whitelist-Eintrag durch den Admin.

### 2.2 Zwei-Faktor-Authentifizierung (2FA)

Nach der Registrierung wirst du zur 2FA-Einrichtung weitergeleitet. **2FA ist Pflicht!**

1. Öffne deine Authenticator-App (Google Authenticator, Authy, etc.)
2. Scanne den QR-Code oder gib den Schlüssel manuell ein
3. Gib den 6-stelligen Code ein
4. Klicke auf **"Aktivieren"**

**Recovery-Codes:**
Nach der 2FA-Aktivierung erhältst du 10 Einmal-Codes. **Speichere diese sicher ab!**

### 2.3 Mail-Account hinzufügen

1. Gehe zu **⚙️ Einstellungen**
2. Klicke auf **"Neuen Account hinzufügen"**
3. Fülle das Formular aus:

#### IMAP-Setup (Alle Provider)

**GMX:**

| Feld | Wert |
|------|------|
| IMAP-Server | imap.gmx.net |
| IMAP-Port | 993 |
| IMAP-Verschl. | SSL |
| SMTP-Server | smtp.gmx.net |
| SMTP-Port | 587 |
| SMTP-Verschl. | STARTTLS |
| Benutzername | deine@gmx.de |
| Passwort | Dein GMX-Passwort |

**Outlook / Hotmail:**

| Feld | Wert |
|------|------|
| IMAP-Server | outlook.office365.com |
| IMAP-Port | 993 |
| SMTP-Server | smtp.office365.com |
| SMTP-Port | 587 |
| Benutzername | deine@outlook.com |
| Passwort | Dein Outlook-Passwort |

**Gmail (mit App-Passwort):**

1. Aktiviere 2-Faktor-Authentifizierung auf [myaccount.google.com](https://myaccount.google.com/security)
2. Gehe zu **Sicherheit** → **App-Passwörter**
3. Wähle **Mail** und **Windows Computer**
4. Google generiert ein 16-stelliges Passwort → **Kopieren**

| Feld | Wert |
|------|------|
| IMAP-Server | imap.gmail.com |
| IMAP-Port | 993 |
| SMTP-Server | smtp.gmail.com |
| SMTP-Port | 587 |
| Benutzername | deine@gmail.com |
| Passwort | 16-stelliges App-Passwort |

#### Google OAuth (empfohlen für Gmail)

OAuth ist sicherer als App-Passwörter und ermöglicht automatische Token-Erneuerung:

1. **Google Cloud Console einrichten:**
   - Gehe zu [Google Cloud Console](https://console.cloud.google.com)
   - Erstelle ein Projekt: "Mail Helper"
   - Aktiviere die **Gmail API**
   - Gehe zu **Anmeldedaten** → **OAuth-Zustimmungsbildschirm** (Extern)
   - Erstelle **OAuth-2.0-Client-ID** (Webapplikation)
   - Redirect-URI hinzufügen: `https://dein-server:5000/settings/mail-account/google/callback`

2. **In Mail Helper:**
   - Wähle **"Google OAuth"** als Methode
   - Gib deine **Client-ID** und **Client-Secret** ein
   - Klicke auf **"Weiter zu Google Anmeldung"**
   - Nach erfolgreicher Anmeldung wird dein Gmail-Konto automatisch hinzugefügt

> 💡 **Tipp:** Bei Gmail empfehlen wir OAuth – kein App-Passwort nötig und sicherer.

#### Verbindung testen

Nach dem Speichern:
1. Gehe zu **Einstellungen** → Mail-Accounts-Tabelle
2. Klicke **"🔌 Verbindung testen"**
3. Bei Erfolg siehst du ✅ mit Anzahl verfügbarer Mails

---

## 3. Das Dashboard

Das Dashboard zeigt deine Emails in einer **3×3 Prioritäts-Matrix**:

|  | Wenig wichtig (1) | Mittel wichtig (2) | Sehr wichtig (3) |
|--|-------------------|--------------------|--------------------|
| **Sehr dringend (3)** | Score 7 🟡 | Score 8 🔴 | Score 9 🔴 |
| **Mittel dringend (2)** | Score 4 🟡 | Score 5 🟡 | Score 6 🟡 |
| **Wenig dringend (1)** | Score 1 🟢 | Score 2 🟢 | Score 3 🟢 |

### Farbcodierung

| Farbe | Score | Bedeutung |
|-------|-------|-----------|
| 🔴 Rot | 8-9 | **Sofort bearbeiten!** Wichtig UND dringend |
| 🟡 Gelb | 4-7 | **Einplanen.** Entweder wichtig ODER dringend |
| 🟢 Grün | 1-3 | **Bei Gelegenheit.** Niedrige Priorität |

### Account-Filter

Bei mehreren Mail-Accounts kannst du das Dashboard filtern:
- **Dropdown oben:** Wähle "Alle Accounts" oder einen spezifischen Account
- **Badge:** Zeigt die gewählte Email-Adresse

---

## 4. Email-Liste & Suche

### Filter

| Filter | Beschreibung |
|--------|--------------|
| 📧 **Account** | Nur Emails von einem bestimmten Mail-Account |
| 📁 **Ordner** | IMAP-Ordner (INBOX, Sent, Trash, etc.) |
| 👁️ **Status** | Gelesen / Ungelesen |
| 🏷️ **Tags** | Nach zugewiesenen Tags filtern |
| 🎨 **Farbe** | Rot / Gelb / Grün |
| ✅ **Erledigt** | Erledigt / Offen / Alle |
| 📎 **Anhänge** | Mit / Ohne Anhänge |

### Semantische Suche

Die semantische Suche findet Emails nach **Bedeutung**, nicht nur nach Keywords.

**Beispiel:** Suche "Rechnung bezahlen" findet auch:
- "Invoice payment reminder"
- "Bitte überweisen Sie den Betrag"
- "Zahlungserinnerung für Bestellung #123"

**So nutzt du sie:**
1. Gib deinen Suchbegriff ein
2. Aktiviere den **🧠 Semantisch**-Toggle
3. Drücke Enter

---

## 5. Email-Detailansicht

### Kalender-Erkennung

Wenn eine Email eine **Kalender-Einladung** enthält (iCalendar/iMIP), wird automatisch eine farbcodierte Karte angezeigt:

| Farbe | Typ | Bedeutung |
|-------|-----|-----------|
| 📅 **Blau** | REQUEST | Termineinladung |
| ✅ **Grün** | REPLY | Terminantwort (Zusage/Absage) |
| ❌ **Rot** | CANCEL | Terminabsage |

**Angezeigte Informationen:**
- Titel des Termins
- Datum und Uhrzeit (Start/Ende)
- Ort (falls vorhanden)
- Organisator
- Teilnehmer mit Status (Akzeptiert/Abgelehnt/Ausstehend)

> 💡 **Tipp:** In der Listenansicht kannst du mit dem **📅 Termine**-Dropdown nach Kalender-Emails filtern.

### KI-Analyse

| Feld | Beschreibung |
|------|--------------|
| **Dringlichkeit** | 1-3 (mit Ampel-Icon) |
| **Wichtigkeit** | 1-3 (mit Ampel-Icon) |
| **Kategorie** | z.B. "Antworten", "Zur Kenntnis", "Ablegen" |
| **Score** | Kombinierter Wert (1-9) |
| **Zusammenfassung** | Deutsche Kurzfassung des Inhalts |
| **Confidence** | Zuverlässigkeit der KI-Analyse (%) |

### Bewertung korrigieren

1. Klicke auf **"✏️ Bewertung korrigieren"**
2. Passe Dringlichkeit/Wichtigkeit an
3. Klicke auf **"💾 Speichern"**

> 💡 Das System **lernt** aus deinen Korrekturen und wird besser!

### IMAP-Aktionen

| Aktion | Beschreibung |
|--------|--------------|
| 🗑️ **Löschen** | Verschiebt in Papierkorb |
| 👁️ **Als gelesen** | Setzt/Entfernt das "Gelesen"-Flag |
| 🚩 **Flaggen** | Markiert als wichtig |
| 📁 **Verschieben** | Verschiebt in anderen IMAP-Ordner |

### Antwort generieren

1. Klicke auf **"✉️ Antwort-Entwurf generieren"**
2. Wähle einen **Ton**:
   - 📜 **Formell** – Professionell, Sie-Form
   - 😊 **Freundlich** – Persönlich, Du-Form möglich
   - ⚡ **Kurz** – Knapp und auf den Punkt
   - 🙅 **Höflich ablehnen** – Diplomatische Absage
3. Bearbeite den Text bei Bedarf
4. **📋 Kopieren** oder **✉️ Absenden** (wenn SMTP konfiguriert)

---

## 6. Tag-Verwaltung

### Tags erstellen

1. Gehe zu **🏷️ Tags**
2. Klicke auf **"➕ Neuer Tag"**
3. Gib einen Namen ein und wähle eine Farbe
4. Klicke auf **"Erstellen"**

### KI-gestützte Tag-Vorschläge

Die KI schlägt Tags basierend auf dem Email-Inhalt vor:
- **≥85%** 🟢 Sehr hohe Übereinstimmung
- **≥75%** 🟡 Gute Übereinstimmung
- **≥70%** ⚫ OK-Übereinstimmung

**Negative Feedback:** Klicke auf **×** bei unpassenden Vorschlägen – das System lernt davon!

---

## 7. Auto-Rules

Auto-Rules führen automatisch Aktionen aus, wenn eine Email Bedingungen erfüllt.

### Regel erstellen

1. Gehe zu **⚡ Auto-Rules**
2. Klicke auf **"➕ Neue Regel"**
3. Definiere Bedingungen (z.B. "Absender enthält 'newsletter'")
4. Definiere Aktionen (z.B. "Tag 'Newsletter' zuweisen")
5. Speichern

### Regeltabelle – Übersicht

Die Regeltabelle zeigt alle deine Regeln mit folgenden Spalten:

| Spalte | Beschreibung |
|--------|--------------|
| **Status** | Klickbarer Toggle-Button: **Aktiv** (grün) oder **Inaktiv** (grau). Klicke zum Umschalten. |
| **Name** | Name der Regel |
| **Learning** | Toggle für Hybrid Score-Learning: **🎓 Aktiv** (violett) oder **Inaktiv** (grau). Wenn aktiv, lernt das System aus den Aktionen dieser Regel. |
| **Priorität** | Ausführungsreihenfolge (1 = höchste Priorität) |
| **Bedingungen** | Anzahl der definierten Bedingungen |
| **Aktionen** | Anzahl der definierten Aktionen |
| **Ausgeführt** | Zähler: Wie oft wurde diese Regel angewendet |
| **Buttons** | Aktions-Buttons für die Regel |

### Aktions-Buttons

| Button | Kürzel | Beschreibung |
|--------|--------|--------------|
| 🧪 **T** | Testen | Testet die Regel gegen vorhandene Emails (ohne Ausführung) |
| ✏️ **B** | Bearbeiten | Öffnet den Editor zum Ändern der Regel |
| 🗑️ **L** | Löschen | Löscht die Regel (mit Bestätigung) |

### Learning pro Regel

Du kannst für jede Regel individuell festlegen, ob sie zum Hybrid Score-Learning beitragen soll:

- **🎓 Aktiv (violett)** – Die Regel trägt zum Training des Classifiers bei
- **Inaktiv (grau)** – Die Regel wird nur ausgeführt, ohne zum Learning beizutragen

**Anwendungsfall:** Deaktiviere Learning für Regeln, die Ausnahmen behandeln oder spezielle Fälle abdecken, die nicht ins allgemeine Modell einfließen sollen.

### Verfügbare Aktionen

- 📁 In Ordner verschieben
- 👁️ Als gelesen markieren
- 🚩 Flaggen
- 🏷️ Tag zuweisen
- 🗑️ Löschen

---

## 8. Antwort-Stile

Unter **Einstellungen → Antwort-Stile** kannst du anpassen, wie die KI Antworten generiert:

| Feld | Beschreibung |
|------|--------------|
| **Anrede-Form** | Auto/Du/Sie |
| **Standard-Anrede** | z.B. "Liebe/r", "Guten Tag" |
| **Grussformel** | z.B. "Beste Grüsse", "Herzliche Grüsse" |
| **Signatur** | Deine Signatur (mehrzeilig) |
| **Zusätzliche Anweisungen** | Spezielle Vorgaben für die KI |

### Account-spezifische Signaturen

Jeder Mail-Account kann eine eigene Signatur haben:
- **Geschäftlich:** Formelle Signatur mit Position
- **Privat:** Lockere Signatur
- **Uni:** Studentische Signatur

---

## 9. KI-Priorisierung

Die KI-Priorisierung nutzt eine **Hybrid-Pipeline**:
- **80% spaCy NLP** – Linguistische Analyse
- **20% Keywords** – 80 strategische Begriffe
- **Ensemble Learning** – Lernt aus deinen Korrekturen

### Personal Classifier (Hybrid Score-Learning)

Das System lernt aus deinen Korrekturen und erstellt ein **persönliches ML-Modell**:

| Modell | Beschreibung |
|--------|---------------|
| **Global Classifier** | Trainiert auf alle User-Korrekturen |
| **Personal Classifier** | Dein individuelles Modell |

**So funktioniert es:**
1. Du korrigierst eine Email-Bewertung (Dringlichkeit/Wichtigkeit/Spam)
2. Das System sammelt deine Korrekturen (min. 5 Stück)
3. Ein persönlicher Classifier wird im Hintergrund trainiert
4. Bei neuen Emails nutzt das System dein persönliches Modell

**Einstellung aktivieren:**
1. Gehe zu **⚙️ Einstellungen**
2. Scrolle zur Sektion **🧠 Machine Learning – Training & Feedback-Loop**
3. Aktiviere den Toggle **"🧠 Persönlich trainierte Modelle bevorzugen"**
4. Das System nutzt dann dein Modell, sobald genug Daten vorhanden sind

> 💡 Bei wenigen Korrekturen fällt das System automatisch auf den Global Classifier zurück.

### VIP-Absender

Unter **🎯 KI-Priorisierung → VIP-Absender** kannst du wichtige Absender definieren, die automatisch höhere Priorität bekommen.

### Email-Anonymisierung (DSGVO)

Wenn du Cloud-AI nutzt, kannst du PII automatisch entfernen:

| Level | Entfernt |
|-------|----------|
| 🔹 **Regex** | EMAIL, PHONE, IBAN, URL |
| 🔺 **Light** | + Personen (PER) |
| 🔺 **Full** | + Organisationen, Orte (ORG, LOC) |

---

## 10. Mail-Verarbeitung & Status

### 10.1 Gesamtablauf: Fetch + Processing

Der komplette Email-Abruf und -Verarbeitung läuft in 4 Haupt-Phasen ab:

#### Phase 1-4: Mail-Abruf (Fetch)

| Phase | Schritt | Beschreibung | Dauer |
|-------|---------|--------------|-------|
| **1** | **IMAP-Connect** | Verbindung zum Mail-Server aufbauen | ~1-3s |
| **2** | **Folder-Scan** | Ordner auflisten, UIDs ermitteln | ~2-10s |
| **3** | **State-Sync** | Server-Status mit lokaler DB abgleichen | ~5-30s |
| **4** | **Fetch-Download** | Neue Emails herunterladen (Header + Body) | ~10-300s |

Nach Phase 4 haben alle neuen Emails **Status 0** (Unbearbeitet) in der Datenbank.

#### Phase 5: Email-Processing (Verarbeitung)

Jede Email durchläuft dann 5 Verarbeitungs-Schritte:

| Status | Schritt | Beschreibung | Dauer |
|--------|---------|--------------|-------|
| **0** | **Unbearbeitet** | Email wurde abgerufen, aber noch nicht analysiert | — |
| **10** | **Embedding** | Semantische Vektorisierung für Suche | ~0.5-2s |
| **20** | **Translation** | Spracherkennung + Übersetzung (wenn nicht DE/EN) | ~1-5s |
| **40** | **AI-Classified** | KI-Priorisierung (Dringlichkeit × Wichtigkeit) | ~2-10s |
| **50** | **Auto-Rules** | Automatische Regelverarbeitung | ~0.1-1s |
| **100** | **Complete** | Vollständig verarbeitet | — |

**Typischer Gesamtablauf:**
```
1. Benutzer klickt "Abrufen" in Einstellungen
2. Fetch-Phase 1-4: 20-60 Sekunden (je nach Anzahl neuer Emails)
3. Processing-Phase: 5-20 Sekunden pro Email (parallel verarbeitet)
4. Dashboard zeigt neue Emails mit KI-Priorisierung
```

**Fehlerbehandlung:**
- Bei Fehler: Status bleibt auf letztem erfolgreichen Schritt
- System setzt Verarbeitung automatisch fort beim nächsten Durchlauf
- Fehler werden in `processing_error` gespeichert und im UI angezeigt

### 10.2 Status-Anzeige im Dashboard

Unter **⚙️ Einstellungen** bei jedem Mail-Account:

- **✅ Grüner Status:** Letzter Abruf erfolgreich
- **⚠️ Gelber Status:** Warnungen (z.B. Quota-Limit erreicht)
- **❌ Roter Status:** Fehler beim Abrufen
- **Delta-Anzeige:** Zeigt Anzahl neuer Emails seit letztem Abruf (z.B. "+3 neue")

**Tooltip:** Fahre mit der Maus über den Status für Details.

### 10.3 Fortsetzung unvollständiger Verarbeitung

Das System ist robust gegen Unterbrechungen:

- **Crash-Recovery:** Nach Server-Neustart werden unvollständige Emails automatisch fortgesetzt
- **Partielle Verarbeitung:** Emails bei Status 10, 20, 40, 50 werden nicht neu begonnen, sondern fortgesetzt
- **Alte ProcessedEmails:** Wenn RawEmail neu verarbeitet wird, werden alte ProcessedEmails gelöscht

**Beispiel:**
```
Email ID 123:
1. Erster Durchlauf: Status 0 → 10 → 20 → [CRASH]
2. Nach Neustart: Status 20 → 40 → 50 → 100 (setzt bei 20 fort)
```

### 10.4 Verarbeitungs-Reihenfolge

**Wichtig:** Emails werden nach **Empfangsdatum** verarbeitet (älteste zuerst), nicht nach ID.

- **Vorteil:** Chronologische Verarbeitung, ältere Emails blockieren nicht
- **Früher:** Nach ID (zufällig bei Multi-Account-Fetch)
- **Jetzt:** `ORDER BY received_at ASC` in der Processing-Pipeline

### 10.5 Granulare Processing-Timestamps (seit v2.2.1)

Das System nutzt **individuelle Timestamps** für jeden Verarbeitungsschritt, statt eines linearen Status-Codes:

| Timestamp-Spalte | Schritt | Bedeutung |
|------------------|---------|-----------|
| `embedding_generated_at` | Embedding | Wann wurde semantische Vektorisierung abgeschlossen? |
| `translation_completed_at` | Translation | Wann wurde Übersetzung abgeschlossen? |
| `ai_classification_completed_at` | AI-Classification | Wann wurde KI-Priorisierung abgeschlossen? |
| `auto_rules_completed_at` | Auto-Rules | Wann wurden Regelverarbeitung abgeschlossen? |

**Vorteile:**
- ✅ **Einzelne Steps nachholbar:** Nur fehlende Schritte werden wiederholt
- ✅ **Kein Datenverlust:** Bei Reset eines Steps bleiben andere erhalten
- ✅ **Audit-Trail:** Genaue Zeitstempel wann was gemacht wurde
- ✅ **Idempotent:** Processing kann beliebig oft laufen

**Beispiel - Nur Translation neu:**
```sql
-- Nur Übersetzung zurücksetzen, Rest bleibt erhalten
UPDATE raw_emails SET 
    translation_completed_at = NULL,
    encrypted_translation_de = NULL
WHERE id = 1276;

-- Beim nächsten Processing:
-- ✅ Embedding: Übersprungen (Timestamp vorhanden)
-- 🔄 Translation: Wird nachgeholt (Timestamp fehlt)
-- ✅ AI-Classification: Übersprungen (Timestamp vorhanden)
-- ✅ Auto-Rules: Übersprungen (Timestamp vorhanden)
```

**Dependencies:**
- **Translation** benötigt: Embedding (für Context)
- **AI-Classification** benötigt: Embedding (für Semantic Features)
- **Auto-Rules** benötigt: AI-Classification (für Kategorien/Scores)

---

## 11. KI-Übersetzer

Der **KI-Übersetzer** ist ein eigenständiges Tool zur Übersetzung von Texten mit automatischer Spracherkennung.

### Zugang

- **URL:** `/translator` oder über die Navigation "🌍 Übersetzer"
- **Voraussetzung:** Angemeldeter Benutzer

### Spracherkennung

Die automatische Spracherkennung nutzt **fastText** (Facebook AI) mit dem Modell `lid.176.bin`:

- ✅ **176 Sprachen** werden erkannt
- ✅ **Sehr schnell** – rein lokal, keine API-Aufrufe
- ✅ **Genau** – zeigt Konfidenz-Prozentsatz

**Verwendung:**
1. Text in das Eingabefeld einfügen
2. Klick auf **"🔍 Sprache erkennen"**
3. Quellsprache wird automatisch gesetzt

### Übersetzungs-Engines

| Engine | Beschreibung | Vorteile |
|--------|--------------|----------|
| **☁️ Cloud (LLM)** | OpenAI, Anthropic, Mistral | Höchste Qualität, alle Sprachpaare |
| **🏠 Lokal (Opus-MT)** | Helsinki-NLP Modelle | Kostenlos, offline, datenschutzfreundlich |

### Cloud-Übersetzung (LLM)

Nutzt deine konfigurierten KI-Provider für hochwertige Übersetzungen:

**Verfügbare Provider:**
- **OpenAI:** gpt-4o-mini, gpt-4o, gpt-4-turbo
- **Anthropic:** claude-sonnet-4-20250514, claude-3-5-haiku-20241022
- **Mistral:** mistral-large-latest, mistral-small-latest

**Vorteile:**
- 🌐 Alle Sprachkombinationen möglich
- 🎯 Kontextbewusste Übersetzungen
- 📝 Erhält Formatierung und Stil

### Lokale Übersetzung (Opus-MT)

Nutzt **Helsinki-NLP/opus-mt** Modelle von Hugging Face:

**Funktionsweise:**
1. Modell wird beim ersten Aufruf heruntergeladen (~300 MB pro Sprachpaar)
2. Modell bleibt im RAM gecached für schnelle Folge-Übersetzungen
3. Läuft vollständig offline nach Download

**Unterstützte Sprachen:**
- Englisch, Deutsch, Französisch, Spanisch, Italienisch
- Portugiesisch, Niederländisch, Russisch, Chinesisch, Japanisch
- Polnisch, Türkisch, Arabisch, Hindi und mehr

**Hinweis:** Nicht alle Sprachpaare haben direkte Modelle. Bei fehlenden Paaren erscheint eine Fehlermeldung.

### Benutzeroberfläche

```
┌────────────────────────────────────────────────────────┐
│  Engine: [☁️ Cloud (LLM) ▼] [🏠 Lokal (Opus-MT) ▼]     │
├────────────────────────────────────────────────────────┤
│  Provider: [OpenAI ▼]    Modell: [gpt-4o-mini ▼]       │
├────────────────────────────────────────────────────────┤
│  Quellsprache: [🔍 Auto] [de ▼]  Zielsprache: [en ▼]   │
├────────────────────────────────────────────────────────┤
│  ┌──────────────────┐   ┌──────────────────┐           │
│  │ Quelltext        │ → │ Übersetzung      │           │
│  │                  │   │                  │           │
│  └──────────────────┘   └──────────────────┘           │
├────────────────────────────────────────────────────────┤
│  [🔍 Sprache erkennen]              [🌍 Übersetzen]    │
└────────────────────────────────────────────────────────┘
```

### Tipps

- **Lange Texte:** Cloud-LLMs haben Token-Limits, teile sehr lange Texte auf
- **Fachbegriffe:** Cloud-LLMs verstehen Kontext besser als Opus-MT
- **Datenschutz:** Nutze Opus-MT für sensible Texte – bleibt lokal
- **Geschwindigkeit:** Opus-MT ist nach dem ersten Laden sehr schnell

---

## 12. Ordner-Audit

Das **Ordner-Audit** (Trash-Audit) analysiert Papierkorb-Ordner auf potenziell wichtige Emails, die versehentlich gelöscht wurden.

### Zugang

- **URL:** `/trash-audit` oder in der Ordner-Ansicht über "🗂️ Ordner-Audit"
- **Voraussetzung:** Angemeldeter Benutzer mit mindestens einem Mail-Account

### Funktionsweise

Das System scannt alle Emails im ausgewählten Ordner (z.B. Papierkorb) und bewertet jede Email anhand von:

| Kriterium | Beschreibung |
|-----------|--------------|
| **🏛️ Vertrauenswürdige Domains** | Bekannte Behörden, Banken, Versicherungen (z.B. admin.ch, sparkasse.de) |
| **📋 Wichtige Keywords** | Betreff-Schlüsselwörter wie "Rechnung", "Kündigung", "Mahnung", "Vertrag" |
| **🔇 Sichere Patterns** | Bekannte unwichtige Emails (Newsletter, Marketing, Werbung) |
| **⭐ VIP-Absender** | Manuell definierte wichtige Absender |

### Scan-Ergebnis

Nach dem Scan zeigt die Detailansicht:

- **Confidence-Score:** Wie sicher ist die Bewertung (0-100%)
- **Kategorie:** Grün (sicher löschen), Gelb (prüfen), Rot (wichtig!)
- **Gründe:** Warum wurde diese Bewertung getroffen

### Konfiguration (Tab)

Im Ordner-Audit-Dialog gibt es einen **"Konfiguration"**-Tab mit folgenden Einstellungen:

#### 🏛️ Vertrauenswürdige Domains

Domains von denen Emails als wichtig eingestuft werden:

```
admin.ch, estv.admin.ch, seco.admin.ch
sparkasse.de, commerzbank.de, ing.de
suva.ch, svazurich.ch, swica.ch
```

#### 📋 Wichtige Keywords

Betreff-Schlüsselwörter die auf wichtige Emails hinweisen:

```
rechnung, invoice, fattura, facture
kündigung, risoluzione, résiliation
mahnung, sollecito, rappel
vertrag, contratto, contrat
```

> 💡 Mehrsprachige Keywords (DE/CH/IT/FR) sind in den Defaults enthalten.

#### 🔇 Sichere Patterns (Betreff)

Betreff-Muster die als unwichtig gelten:

```
newsletter, digest, marketing
rabatt, gutschein, sonderangebot
```

#### 🔇 Sichere Patterns (Absender)

Absender-Muster die als unwichtig gelten:

```
@newsletter., @marketing., @promo.
noreply@, no-reply@, donotreply@
```

#### ⭐ VIP-Absender

Wichtige Absender mit erweiterten Matching-Optionen:

| Format | Beispiel | Beschreibung |
|--------|----------|--------------|
| **Exakt** | `chef@firma.ch` | Nur diese eine Adresse |
| **Wildcard** | `*@firma.ch` | Alle Adressen von firma.ch |
| **Regex** | `/.*@(firma|konzern)\.ch/` | Regex-Pattern (mit `/.../' umschließen) |

### Defaults laden

Klicke auf **"📥 Defaults laden"** um vordefinierte Listen für mehrere Länder/Sprachen zu importieren:

- **CH:** Schweizer Behörden (admin.ch, ahv-iv.ch, etc.)
- **DE:** Deutsche Behörden (bund.de, arbeitsagentur.de, etc.)
- **IT:** Italienische Behörden (gov.it, inps.it, etc.)
- **FR:** Französische Behörden (gouv.fr, impots.gouv.fr, etc.)

Die Defaults enthalten auch mehrsprachige Keywords für:
- 📄 Rechnungen/Finanzen
- 📋 Verträge/Kündigungen
- ⚠️ Mahnungen/Fristen
- 🏛️ Behördliche Korrespondenz

### VIP-Absender aus Email hinzufügen

In der Email-Detailansicht kannst du einen Absender direkt als VIP markieren:

1. Öffne die Email
2. Klicke auf **"⭐ Als VIP Absender"**
3. Wähle ob für alle Accounts oder nur diesen Account
4. Speichern

---

## 13. Einstellungen

### Mail-Accounts

- **Hinzufügen/Bearbeiten** von IMAP/SMTP-Accounts
- **Account-Signatur** für individuelle Signaturen
- **AI-Analyse beim Abruf** aktivieren/deaktivieren
- **UrgencyBooster** für Trusted Senders

### KI-Provider

| Provider | Beschreibung |
|----------|--------------|
| **Ollama (lokal)** | Läuft auf deinem Server, kostenlos |
| **OpenAI** | GPT-Modelle via API |
| **Anthropic** | Claude via API |
| **Mistral** | Mistral via API |

### Drei-Modell-System

| Einstellung | Zweck |
|-------------|-------|
| **Embedding Model** | Semantische Suche & Tag-Vorschläge |
| **Base Model** | Schnelle Email-Analyse |
| **Optimize Model** | Tiefe Analyse bei "Optimieren" |

---

## 14. Sicherheit & Datenschutz

### Zero-Knowledge-Architektur

- **Alle Daten verschlüsselt** mit AES-256-GCM
- **Server sieht niemals Klartext** – Entschlüsselung nur im Browser
- **Passwort = Schlüssel** – Bei Verlust sind Daten unwiederbringlich

### Verwendete Kryptographie

| Komponente | Algorithmus |
|------------|-------------|
| **Passwort-Hashing** | PBKDF2-HMAC-SHA256 (600.000 Iterationen) |
| **Datenverschlüsselung** | AES-256-GCM |
| **2FA** | TOTP (SHA-1, 30s, 6 Ziffern) |

---

## 15. Fehlerbehebung

### "Emails werden nicht abgerufen"

1. Prüfe IMAP-Zugangsdaten in den Einstellungen
2. Teste die Verbindung mit **"🔌 Verbindung testen"**
3. Prüfe Celery-Worker: `systemctl status mail-helper-worker`

### "KI-Analyse schlägt fehl"

1. Prüfe Ollama: `systemctl status ollama`
2. Prüfe API-Keys für Cloud-Provider
3. Prüfe Logs: `journalctl -u mail-helper -f`

### "2FA-Code nicht akzeptiert"

1. **Zeit synchronisieren:** TOTP ist zeitbasiert
2. **Recovery-Code verwenden:** Falls nichts hilft

### "Passwort vergessen"

> ⚠️ **Nicht wiederherstellbar.** Zero-Knowledge bedeutet: Ohne Passwort kann niemand deine Daten entschlüsseln. Du musst einen neuen Account erstellen.

---

## Anhang: Tastenkürzel

| Kürzel | Funktion |
|--------|----------|
| `/` | Zur Suche springen |
| `g` dann `d` | Gehe zu Dashboard |
| `g` dann `l` | Gehe zu Liste |
| `g` dann `t` | Gehe zu Tags |
| `g` dann `s` | Gehe zu Einstellungen |

---

## Anhang: Glossar

| Begriff | Erklärung |
|---------|-----------|
| **DEK** | Data Encryption Key – verschlüsselt deine Emails |
| **KEK** | Key Encryption Key – verschlüsselt den DEK |
| **Embedding** | Semantischer Fingerabdruck eines Textes |
| **IMAP** | Protokoll zum Abrufen von Emails |
| **SMTP** | Protokoll zum Versenden von Emails |
| **Celery** | Hintergrund-Task-Queue für asynchrone Jobs |
| **Zero-Knowledge** | Server-Architektur ohne Klartext-Zugriff |

---

*Dieses Handbuch wurde für KI-Mail-Helper v2.0 (Multi-User Edition) erstellt.*
