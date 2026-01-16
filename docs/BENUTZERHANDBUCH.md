# 📧 KI-Mail-Helper – Benutzerhandbuch

**Version:** 2.0.0 (Multi-User Edition)  
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
10. [Einstellungen](#11-einstellungen)
11. [Sicherheit & Datenschutz](#12-sicherheit--datenschutz)
12. [Fehlerbehebung](#13-fehlerbehebung)

---

## 1. Einführung

KI-Mail-Helper ist ein selbst-gehosteter Email-Organizer mit Multi-User-Support, der künstliche Intelligenz nutzt, um deine Emails automatisch zu analysieren, zu priorisieren und zu beantworten.

### Kernfunktionen

| Feature | Beschreibung |
|---------|--------------|
| **🎯 3×3 Prioritäts-Matrix** | Automatische Bewertung nach Dringlichkeit × Wichtigkeit |
| **🧠 KI-Priorisierung** | spaCy NLP (80%) + Keywords (20%) + Ensemble Learning |
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

## 10. Einstellungen

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

## 11. Sicherheit & Datenschutz

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

## 12. Fehlerbehebung

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
