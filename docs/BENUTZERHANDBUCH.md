# 📧 KI-Mail-Helper – Benutzerhandbuch

**Version:** 1.4.0  
**Stand:** 10. Januar 2026

---

## Inhaltsverzeichnis

1. [Einführung](#1-einführung)
2. [Erste Schritte](#2-erste-schritte)
   - 2.1 Registrierung
   - 2.2 Zwei-Faktor-Authentifizierung (2FA)
   - 2.3 Ersten Mail-Account hinzufügen
3. [Das Dashboard](#3-das-dashboard)
   - 3.1 Die 3×3 Prioritäts-Matrix
   - 3.2 Farbcodierung verstehen
4. [Email-Liste](#4-email-liste)
   - 4.1 Filter verwenden
   - 4.2 Sortierung
   - 4.3 Semantische Suche
5. [Email-Detailansicht](#5-email-detailansicht)
   - 5.1 KI-Analyse verstehen
   - 5.2 Tags verwalten
   - 5.3 Bewertung korrigieren
   - 5.4 Email optimieren / neu verarbeiten
   - 5.5 IMAP-Aktionen
   - 5.6 Antwort generieren und senden
   - 5.7 Anonymisierte Version ansehen
   - 5.8 Ähnliche Emails finden
6. [Tag-Verwaltung](#6-tag-verwaltung)
   - 6.1 Tags erstellen
   - 6.2 Tags bearbeiten und löschen
   - 6.3 KI-gestützte Tag-Vorschläge
7. [Auto-Rules (Automatische Regeln)](#7-auto-rules-automatische-regeln)
   - 7.1 Was sind Auto-Rules?
   - 7.2 Regel erstellen
   - 7.3 Verfügbare Bedingungen
   - 7.4 Verfügbare Aktionen
   - 7.5 Vorgefertigte Templates
   - 7.6 Regel testen (Dry-Run)
   - 7.7 Statistiken
8. [Antwort-Stile](#8-antwort-stile)
   - 8.1 Globale Einstellungen
   - 8.2 Stil-spezifische Anpassungen
   - 8.3 Merge-Logik verstehen
   - 8.4 Preview-Funktion
9. [KI-Priorisierung](#9-ki-priorisierung)
   - 9.1 Was ist KI-Priorisierung?
   - 9.2 Email-Anonymisierung (DSGVO-konform)
   - 9.3 VIP-Absender konfigurieren
   - 9.4 Keywords anpassen
   - 9.5 Scoring-Gewichte
   - 9.6 User-Domains (Intern/Extern)
   - 9.7 Ensemble Learning
10. [IMAP-Diagnostics](#10-imap-diagnostics)
11. [Einstellungen](#11-einstellungen)
   - 11.1 Mail-Accounts verwalten
   - 11.2 SMTP konfigurieren (Email-Versand)
   - 11.3 KI-Provider konfigurieren
   - 11.4 Absender & Abruf (Trusted Senders + AI-Control)
   - 11.5 Passwort ändern
   - 11.6 2FA & Recovery-Codes
12. [Sicherheit & Datenschutz](#12-sicherheit--datenschutz)
13. [Fehlerbehebung](#13-fehlerbehebung)

---

## 1. Einführung

KI-Mail-Helper ist ein selbst-gehosteter Email-Organizer, der künstliche Intelligenz nutzt, um deine Emails automatisch zu analysieren, zu priorisieren und zu beantworten.

**Kernfunktionen:**

| Feature | Beschreibung |
|---------|--------------|
| **🎯 3×3 Prioritäts-Matrix** | Automatische Bewertung nach Dringlichkeit × Wichtigkeit |
| **🧠 KI-Priorisierung** | spaCy NLP (80%) + Keywords (20%) + Ensemble Learning |
| **�️ Email-Anonymisierung** | spaCy PII-Entfernung vor Cloud-AI (DSGVO-konform) |
| **📊 Confidence Tracking** | Transparenz über AI-Analyse-Qualität |
| **�🔍 Semantische Suche** | Finde Emails nach Bedeutung, nicht nur Keywords |
| **✉️ KI-Antworten + Versand** | Generierte Antwort-Entwürfe direkt per SMTP senden |
| **⚡ Auto-Rules Engine** | Automatische Aktionen basierend auf Regeln |
| **🏷️ Intelligente Tags** | KI schlägt Tags vor, lernt aus deinem Verhalten |
| **📁 IMAP-Aktionen** | Löschen, Verschieben, Flaggen direkt aus der App |
| **🔐 Zero-Knowledge** | Server sieht niemals Klartext-Daten |
| **📧 Multi-Account** | IMAP & Gmail OAuth Support |

**Was diese App NICHT ist:**
- Kein vollwertiger Email-Client (aber Antworten senden geht!)
- Kein Spam-Filter (das macht dein Email-Provider)
- Keine Cloud-Lösung (läuft auf deinem eigenen Server)

---

## 2. Erste Schritte

### 2.1 Registrierung

> **📸 Screenshot:** Registrierungs-Formular (register.html)  
> *Zeige: Username, Email, Passwort-Felder, Passwort-Anforderungen*

![Registrierungs-Formular](images/screenshots/register.png)

1. Öffne die App im Browser: `https://dein-server:5001`
2. Klicke auf **"Registrieren"**
3. Fülle das Formular aus:
   - **Benutzername:** 3-80 Zeichen
   - **E-Mail:** Deine Email-Adresse
   - **Passwort:** Mindestens 24 Zeichen (OWASP-Standard)

**Passwort-Anforderungen:**
- Mindestens 24 Zeichen
- Groß- und Kleinbuchstaben
- Mindestens eine Zahl
- Mindestens ein Sonderzeichen
- Keine einfachen Sequenzen (abc, 123, qwerty)

> ⚠️ **Wichtig:** Dieses Passwort ist dein Master-Passwort. Es wird verwendet, um alle deine Daten zu verschlüsseln. Wenn du es vergisst, sind deine Daten unwiederbringlich verloren!

---

### 2.2 Zwei-Faktor-Authentifizierung (2FA)

> **📸 Screenshot:** 2FA-Setup mit QR-Code (setup_2fa.html)  
> *Zeige: QR-Code, manueller Schlüssel, Eingabefeld für Code*

![2FA-Setup mit QR-Code](images/screenshots/2fa-setup.png)

Nach der Registrierung wirst du automatisch zur 2FA-Einrichtung weitergeleitet. **2FA ist Pflicht** – du kannst die App ohne aktivierte 2FA nicht nutzen.

**Einrichtung:**
1. Öffne deine Authenticator-App (Google Authenticator, Authy, etc.)
2. Scanne den QR-Code oder gib den Schlüssel manuell ein
3. Gib den 6-stelligen Code aus der App ein
4. Klicke auf **"Aktivieren"**

> **📸 Screenshot:** Recovery-Codes Anzeige (recovery_codes.html)  
> *Zeige: Liste der 10 Codes, Download-Button, Warnung*

![Recovery-Codes](images/screenshots/recovery-codes.png)

**Recovery-Codes:**
Nach der 2FA-Aktivierung erhältst du 10 Einmal-Codes. **Speichere diese sicher ab!** Sie sind dein Backup, falls du den Zugriff auf deine Authenticator-App verlierst.

- Klicke auf **"Als .txt herunterladen"**
- Speichere die Datei an einem sicheren Ort (z.B. Passwort-Manager)
- Jeder Code kann nur einmal verwendet werden

---

### 2.3 Ersten Mail-Account hinzufügen

> **📸 Screenshot:** Einstellungen > Mail-Account hinzufügen (settings.html)  
> *Zeige: "Neuen Account hinzufügen" Button, Account-Liste*

![Einstellungen - Mail-Accounts](images/screenshots/settings-mail-accounts.png)

1. Nach dem Login: Gehe zu **⚙️ Einstellungen**
2. Scrolle zu **"Mail-Accounts"**
3. Klicke auf **"Neuen Account hinzufügen"**

> **📸 Screenshot:** Mail-Account Formular (add_mail_account.html)  
> *Zeige: Name, IMAP-Server, Port, Verschlüsselung, Username, Passwort*

![Mail-Account Formular](images/screenshots/add-mail-account.png)

**Für IMAP (GMX, Web.de, etc.):**

| Feld | Beispiel (GMX) |
|------|----------------|
| Name | GMX Postfach |
| IMAP-Server | imap.gmx.net |
| Port | 993 |
| Verschlüsselung | SSL |
| Benutzername | deine@email.de |
| Passwort | Dein Email-Passwort |

**Für Gmail (OAuth):**
1. Wähle **"Google OAuth"** als Methode
2. Klicke auf **"Mit Google verbinden"**
3. Melde dich bei Google an und erteile die Berechtigung

> 💡 **Tipp:** Bei Gmail empfehlen wir OAuth – kein App-Passwort nötig und sicherer.

---

## 3. Das Dashboard

> **📸 Screenshot:** Dashboard mit gefüllter Matrix (dashboard.html)  
> *Zeige: 3x3 Matrix mit Zahlen, Farben, Info-Box oben*

![Dashboard mit 3×3 Prioritäts-Matrix](images/screenshots/dashboard.png)

Das Dashboard ist deine Zentrale. Hier siehst du auf einen Blick, welche Emails deine Aufmerksamkeit brauchen.

**Account-Filter:**
Wenn du mehrere Mail-Accounts hast, kannst du das Dashboard auf einen spezifischen Account filtern:
- **Dropdown oben:** Wähle "Alle Accounts" oder einen spezifischen Account (Email-Adresse)
- **Badge:** Zeigt die gewählte Email-Adresse wenn gefiltert
- **Mail-Anzahl:** Im Dropdown siehst du "(47 Mails)" für den gewählten Account
- **Persistenz:** Filter bleibt beim Reload erhalten (URL-Parameter)

> 💡 Der Account-Filter wirkt auf Matrix, Ampel-Ansicht UND Statistik. Perfekt, um einen spezifischen Posteingang zu fokussieren!

### 3.1 Die 3×3 Prioritäts-Matrix

Die Matrix kombiniert zwei Dimensionen:

|  | Wenig wichtig (1) | Mittel wichtig (2) | Sehr wichtig (3) |
|--|-------------------|--------------------|--------------------|
| **Sehr dringend (3)** | Score 7 🟡 | Score 8 🔴 | Score 9 🔴 |
| **Mittel dringend (2)** | Score 4 🟡 | Score 5 🟡 | Score 6 🟡 |
| **Wenig dringend (1)** | Score 1 🟢 | Score 2 🟢 | Score 3 🟢 |

**Dringlichkeit** (Y-Achse): Wie schnell musst du reagieren?
- 3 = Heute/Sofort
- 2 = Diese Woche
- 1 = Kann warten

**Wichtigkeit** (X-Achse): Wie bedeutsam ist die Email?
- 3 = Kritisch für Arbeit/Leben
- 2 = Relevant, aber nicht kritisch
- 1 = Nice-to-know, Newsletter, etc.

### 3.2 Farbcodierung verstehen

| Farbe | Score | Bedeutung |
|-------|-------|-----------|
| 🔴 Rot | 8-9 | **Sofort bearbeiten!** Wichtig UND dringend |
| 🟡 Gelb | 4-7 | **Einplanen.** Entweder wichtig ODER dringend |
| 🟢 Grün | 1-3 | **Bei Gelegenheit.** Weder besonders wichtig noch dringend |

> 💡 Die Zahl in jeder Zelle zeigt, wie viele Emails in dieser Kategorie sind. Klicke auf eine Zelle, um diese Emails zu sehen.

---

## 4. Email-Liste

> **📸 Screenshot:** Email-Liste mit Filtern (list_view.html)  
> *Zeige: Filter-Leiste oben, Email-Karten darunter, Farb-Badges*

![Email-Liste mit Filtern](images/screenshots/list-view.png)

Die Listen-Ansicht zeigt alle deine Emails mit den wichtigsten Informationen.

### 4.1 Filter verwenden

> **📸 Screenshot:** Filter-Dropdown aufgeklappt  
> *Zeige: Account, Ordner, Status, Tags, Farbe Dropdowns*

![Filter-Dropdown](images/screenshots/filter-dropdown.png)

**Verfügbare Filter:**

| Filter | Beschreibung |
|--------|--------------|
| 📧 **Account** | Nur Emails von einem bestimmten Mail-Account |
| 📁 **Ordner** | IMAP-Ordner (INBOX, Sent, Trash, etc.) |
| 👁️ **Status** | Gelesen / Ungelesen |
| 🏷️ **Tags** | Nach zugewiesenen Tags filtern |
| 🎨 **Farbe** | Rot / Gelb / Grün |
| ✅ **Erledigt** | Erledigt / Offen / Alle |
| 📎 **Anhänge** | Mit / Ohne Anhänge |
| 🚩 **Flagged** | Geflaggt / Nicht geflaggt |

**Filter kombinieren:** Alle Filter wirken zusammen. "Account: GMX" + "Farbe: Rot" zeigt nur rote GMX-Emails.

### 4.2 Sortierung

| Sortierung | Beschreibung |
|------------|--------------|
| **Datum** | Nach Empfangsdatum (neueste/älteste zuerst) |
| **Score** | Nach Prioritäts-Score (höchste/niedrigste zuerst) |
| **Absender** | Alphabetisch nach Absender |

Klicke auf den **Sortier-Button** (↑↓) um die Reihenfolge zu ändern.

### 4.3 Semantische Suche

> **📸 Screenshot:** Suchfeld mit Semantik-Toggle und Ergebnis-Liste  
> *Zeige: Suchfeld, "🧠 Semantic" Toggle, Ergebnisse mit Similarity-Score*

![Semantische Suche](images/screenshots/semantic-search.png)

Die semantische Suche findet Emails nach **Bedeutung**, nicht nur nach Keywords.

**Beispiel:** Suche "Rechnung bezahlen" findet auch:
- "Invoice payment reminder"
- "Bitte überweisen Sie den Betrag"
- "Zahlungserinnerung für Bestellung #123"

**So nutzt du sie:**

1. Gib deinen Suchbegriff ein
2. Aktiviere den **🧠 Semantisch**-Toggle
3. Drücke Enter oder klicke auf Suchen
4. Ergebnisse zeigen einen **Similarity-Score** (z.B. "87%")

**Normal vs. Semantisch:**

| Modus | Findet | Beispiel |
|-------|--------|----------|
| **Normal** | Exakte Wörter | "Rechnung" → nur Emails mit "Rechnung" |
| **Semantisch** | Ähnliche Bedeutung | "Rechnung" → auch "Invoice", "Zahlung", etc. |

> 💡 **Tipp:** Semantische Suche funktioniert am besten mit **vollständigen Sätzen** oder **Beschreibungen** statt einzelner Wörter.

---

## 5. Email-Detailansicht

> **📸 Screenshot:** Email-Detail komplett (email_detail.html)  
> *Zeige: Header mit Betreff/Absender, KI-Analyse-Box, Body, Action-Buttons*

![Email-Detailansicht](images/screenshots/email-detail.png)

Klicke auf eine Email in der Liste, um die Detailansicht zu öffnen.

### 5.1 KI-Analyse verstehen

> **📸 Screenshot:** KI-Analyse Box (oberer Teil der Detail-Ansicht)  
> *Zeige: Dringlichkeit, Wichtigkeit, Kategorie, Score, Zusammenfassung*

![KI-Analyse Box](images/screenshots/ki-analyse.png)

Die KI analysiert jede Email und liefert:

| Feld | Beschreibung |
|------|--------------|
| **Dringlichkeit** | 1-3 (mit Ampel-Icon) |
| **Wichtigkeit** | 1-3 (mit Ampel-Icon) |
| **Kategorie** | z.B. "Antworten", "Zur Kenntnis", "Ablegen" |
| **Score** | Kombinierter Wert (1-9) |
| **Zusammenfassung** | Deutsche Kurzfassung des Inhalts |
| **Übersetzung** | Falls Originalsprache nicht Deutsch |

### 5.2 Tags verwalten

> **📸 Screenshot:** Tag-Bereich in Email-Detail  
> *Zeige: Zugewiesene Tags als Badges, "+ Tag hinzufügen" Button*

![Tag-Bereich in Email-Detail](images/screenshots/email-tags.png)

**Tags hinzufügen:**
1. Klicke auf **"+ Tag hinzufügen"**
2. Wähle einen existierenden Tag aus der Liste
3. Der Tag erscheint sofort als Badge

**Tags entfernen:**
- Klicke auf das **X** neben dem Tag-Badge

### 5.3 Bewertung korrigieren

> **📸 Screenshot:** "Bewertung korrigieren" Modal  
> *Zeige: Radio-Buttons für Dringlichkeit/Wichtigkeit, Kategorie-Dropdown, Spam-Toggle*

![Bewertung korrigieren Modal](images/screenshots/correct-rating.png)

Wenn die KI falsch lag, kannst du die Bewertung korrigieren:

1. Klicke auf **"✏️ Bewertung korrigieren"** (gelber Button oben in der Detail-Ansicht)
2. Passe **Dringlichkeit** (1-3) und **Wichtigkeit** (1-3) mit Radio-Buttons an
3. Ändere ggf. die **Kategorie** (Nur Information / Aktion erforderlich / Dringend)
4. Setze den **Spam-Toggle** falls die E-Mail Spam ist
5. Füge optional eine **Notiz** hinzu (warum du korrigiert hast)
6. Klicke auf **"💾 Speichern & als Training markieren"**

**Was passiert nach dem Speichern?**

✅ **Sofortige Anzeige:** Deine Korrektur wird in der Detail-Ansicht als "User-Korrektur" Sektion angezeigt  
✅ **Online-Learning:** Das System lernt **sofort** aus deiner Korrektur (kein Neutraining nötig)  
✅ **Priorität:** User-Korrekturen haben höchste Priorität in der Anzeige (user_override > optimize > initial)  
✅ **4 Classifier:** Trainiert werden Dringlichkeit, Wichtigkeit, Spam und Kategorie  
✅ **Embeddings:** Nutzt lokales Ollama (all-minilm:22m) für Vektorisierung  

> 💡 **Wichtig:** Das Learning funktioniert nur wenn Ollama läuft! Cloud-APIs (OpenAI/Claude) können die Initial-Analyse machen, aber das Training braucht lokale Embeddings.

> 🎯 **Tipp:** Je mehr du korrigierst, desto besser wird die KI bei ähnlichen E-Mails! Das System merkt sich Muster über Embeddings.

### 5.4 Email optimieren / neu verarbeiten

> **📸 Screenshot:** Buttons "Optimieren" und "Neu verarbeiten"  
> *Zeige: Die beiden Action-Buttons*

![Optimieren und Neu verarbeiten Buttons](images/screenshots/optimize-buttons.png)

| Button | Funktion |
|--------|----------|
| **🚀 Optimieren** | Nutzt ein größeres KI-Modell für tiefere Analyse |
| **🔄 Neu verarbeiten** | Führt die Standard-Analyse erneut durch |

"Optimieren" ist nützlich bei komplexen Emails, wo die schnelle Erst-Analyse nicht ausreicht.

### 5.5 IMAP-Aktionen

> **📸 Screenshot:** IMAP-Action Buttons (Löschen, Flag, Read, Move)  
> *Zeige: Die Buttons mit Icons*

![IMAP-Action Buttons](images/screenshots/imap-actions.png)

Du kannst Emails direkt auf dem IMAP-Server bearbeiten:

| Aktion | Button | Beschreibung |
|--------|--------|--------------|
| **Löschen** | 🗑️ | Verschiebt in Papierkorb (oder löscht permanent) |
| **Als gelesen** | 👁️ | Setzt/Entfernt das "Gelesen"-Flag |
| **Flaggen** | 🚩 | Markiert als wichtig (Toggle) |
| **Verschieben** | 📁 | Verschiebt in anderen IMAP-Ordner |

> ⚠️ Diese Aktionen werden **sofort auf dem IMAP-Server** ausgeführt! Du siehst die Änderung auch in deinem normalen Email-Client.

### 5.6 Antwort generieren und senden

> **📸 Screenshot:** Reply-Draft Modal mit Ton-Auswahl und generiertem Text  
> *Zeige: Ton-Buttons, generierte Antwort, "Absenden" Button*

![Reply-Draft Generator](images/screenshots/reply-draft.png)

**Schritt 1: Entwurf generieren**

1. Klicke auf **"✉️ Antwort-Entwurf generieren"**
2. Wähle einen **Ton**:

| Ton | Icon | Beschreibung |
|-----|------|--------------|
| **Formell** | 📜 | Geschäftlich, höflich, professionell |
| **Freundlich** | 😊 | Warm, persönlich, aber respektvoll |
| **Kurz** | ⚡ | Knapp und auf den Punkt |
| **Höfliche Ablehnung** | 🙅 | Freundlich, aber bestimmt absagen |

3. Klicke auf **"Generieren"**
4. Die KI erstellt einen Antwort-Entwurf basierend auf dem Thread-Kontext

**Schritt 2: Bearbeiten (optional)**
- Der Text erscheint in einem Textfeld
- Du kannst ihn beliebig anpassen

**Schritt 3: Senden oder Kopieren**

| Option | Voraussetzung | Beschreibung |
|--------|---------------|--------------|
| **📋 Kopieren** | Immer verfügbar | Text in Zwischenablage, dann in Mail-Client einfügen |
| **✉️ Absenden** | SMTP konfiguriert | Email direkt aus der App senden |

> 💡 **SMTP-Versand:** Wenn SMTP konfiguriert ist (siehe Einstellungen), kannst du Antworten **direkt aus der App senden**. Die Email landet korrekt im Thread (In-Reply-To Header) und wird auch im Sent-Ordner gespeichert.

### 5.7 Anonymisierte Version ansehen

> **🆕 Feature seit Version 1.3.0**

Wenn du **Email-Anonymisierung** aktiviert hast (siehe [Abschnitt 9.2](#92-email-anonymisierung-dsgvo-konform)), findest du in der Email-Detail-Ansicht einen neuen Tab:

**Tab-Leiste:**
- 🖼️ **Gerendert** (HTML-Ansicht)
- 📄 **Rohtext** (Plain Text)
- 🛡️ **Anonymisiert** (33 Entities erkannt, Level 3)

**Anonymisierte Ansicht:**

Der Tab zeigt die **bereinigte Version**, die an die Cloud-AI übertragen wurde. Alle personenbezogenen Daten wurden durch Platzhalter ersetzt:

**Beispiel:**
```
Original:
"Hallo Hans Müller, vielen Dank für Ihre Nachricht. 
Bitte rufen Sie uns unter 044 123 45 67 an oder 
schreiben Sie an kontakt@firma.ch."

Anonymisiert (Level 3 Full):
"Hallo [PERSON_1], vielen Dank für Ihre Nachricht.
Bitte rufen Sie uns unter [PHONE_1] an oder
schreiben Sie an [EMAIL_1]."
```

**Anzeige-Informationen:**

| Element | Beschreibung |
|---------|--------------|
| **Entity-Count** | Anzahl erkannter Entities (z.B. "33 Entities") |
| **Level** | Sanitization-Level (1-3: Regex, Light, Full) |
| **Iframe** | Sichere HTML-Darstellung (kein Script-Ausführung) |

**Nutzen:**
- **Transparenz:** Sehe, welche Daten an Cloud-AI gehen
- **Kontrolle:** Prüfe, ob sensible Infos entfernt wurden
- **DSGVO:** Dokumentiere PII-Entfernung für Compliance

> 💡 **Tipp:** Bei unerwarteten Ergebnissen (zu viel/wenig Anonymisierung) kannst du das Level in `/whitelist` anpassen.

### 5.8 Ähnliche Emails finden

> **📸 Screenshot:** "Ähnliche Emails" Card in der Detailansicht  
> *Zeige: Liste mit 3-5 ähnlichen Emails, Similarity-Score*

![Ähnliche Emails](images/screenshots/similar-emails.png)

Unter der Email-Ansicht findest du eine **"Ähnliche Emails"**-Sektion:

- Zeigt Emails mit ähnlichem Inhalt (semantische Ähnlichkeit)
- Score zeigt Übereinstimmung (z.B. "87%")
- Klicke auf eine Email, um sie zu öffnen

**Nutzen:**
- Finde verwandte Konversationen
- Entdecke wiederholte Anfragen
- Erkenne Newsletter-Muster

---

## 6. Tag-Verwaltung

> **📸 Screenshot:** Tag-Verwaltung Seite (/tags)  
> *Zeige: Tag-Liste mit Farben, Email-Counts, Buttons*

![Tag-Verwaltung](images/screenshots/tags-management.png)

Über **🏷️ Tags** in der Navigation erreichst du die Tag-Verwaltung.

### 6.1 Tags erstellen

> **📸 Screenshot:** "Neuer Tag" Modal  
> *Zeige: Name-Eingabe, Farb-Auswahl (7 Kreise)*

![Neuer Tag Modal](images/screenshots/new-tag-modal.png)

1. Klicke auf **"➕ Neuer Tag"**
2. Gib einen Namen ein (max. 50 Zeichen)
3. Wähle eine Farbe aus den 7 Optionen
4. Klicke auf **"Erstellen"**

**Verfügbare Farben:**
- 🔵 Blau (#3B82F6)
- 🟢 Grün (#10B981)
- 🟡 Gelb (#F59E0B)
- 🔴 Rot (#EF4444)
- 🟣 Lila (#8B5CF6)
- 🩷 Pink (#EC4899)
- ⚫ Grau (#6B7280)

### 6.2 Tags bearbeiten und löschen

Jeder Tag zeigt:
- **Name** als farbiges Badge
- **Anzahl** der zugewiesenen Emails

**Bearbeiten:** Klicke auf den ✏️ Stift-Button  
**Löschen:** Klicke auf den 🗑️ Papierkorb-Button (mit Bestätigung)

> ⚠️ Beim Löschen eines Tags werden alle Zuweisungen entfernt. Die Emails selbst bleiben erhalten.

### 6.3 KI-gestützte Tag-Vorschläge

> **📸 Screenshot:** Tag-Vorschläge in Email-Detail (Suggestion-Badges)  
> *Zeige: Vorgeschlagene Tags als klickbare Badges mit × Buttons*

![Tag-Vorschläge](images/screenshots/tag-suggestions.png)

Die KI schlägt automatisch Tags vor, basierend auf semantischer Ähnlichkeit.

#### Tag-Embedding-Hierarchie (Learning-System)

Das System nutzt eine 3-stufige Hierarchie für beste Ergebnisse:

| Stufe | Quelle | Qualität | Beschreibung |
|-------|--------|----------|--------------|
| 1️⃣ **Learned** | Aggregierte Embeddings aus zugewiesenen Emails | ⭐⭐⭐⭐⭐ | Beste Ergebnisse! Lernt aus deinem Verhalten |
| 2️⃣ **Description** | Tag-Beschreibung als Text-Embedding | ⭐⭐⭐⭐ | Gut für neue Tags mit Beschreibung |
| 3️⃣ **Name** | Nur Tag-Name als Embedding | ⭐⭐⭐ | Fallback wenn keine anderen Daten vorhanden |

**So funktioniert's:**
1. Jede Email bekommt ein **Embedding** (semantischer Fingerabdruck)
2. Jeder Tag hat ein Embedding (learned/description/name)
3. Die KI berechnet: "Wie ähnlich ist diese Email zu Emails mit Tag X?"
4. Tags mit hoher Ähnlichkeit werden vorgeschlagen

**Confidence-Levels:**
- **≥85%** 🟢 Sehr hohe Übereinstimmung (grüner Rand)
- **≥75%** 🟡 Gute Übereinstimmung (oranger Rand)
- **≥70%** ⚫ OK-Übereinstimmung (grauer Rand)

**In Email-Detail:**
- Klick auf **Badge** → Tag wird zugewiesen
- Klick auf **×** → Tag wird abgelehnt (Negative Feedback)

#### Negative Feedback (Phase F.3)

> **Neu seit 2026-01-06:** Das System lernt auch von Ablehnungen!

**Workflow:**
1. Email über "Projekt X" wird geöffnet
2. KI schlägt unpassenden Tag "Arbeit" vor (75% Match)
3. Du klickst auf **×** (Reject-Button)
4. System speichert dies als **negative example**
5. Nächste ähnliche Email: "Arbeit" bekommt Penalty und wird nicht mehr vorgeschlagen! ✅

**Wie Penalty funktioniert:**
- System berechnet `negative_embedding` (Mittelwert aller Ablehnungen)
- Bei neuer Suggestion: Penalty = Similarity-Verhältnis × Count-Bonus
- Penalty wird vom Score abgezogen (0-20%)
- Je mehr Rejects (Count-Bonus), desto stärker die Penalty

**Beispiel:**
```
Tag "Arbeit" für Freizeit-Email:
- Original Similarity: 75%
- Negative Similarity: 72%
- 3 Rejects gespeichert
→ Penalty: ~14% (ratio 0.96 × count_factor 1.15)
→ Final Score: 61% → unter Threshold → NICHT vorgeschlagen ✅
```

#### Tag-Suggestion-Queue (`/tag-suggestions`)

> **📸 Screenshot:** Tag-Suggestions Queue Seite  
> *Zeige: Pending-Liste mit Approve/Reject/Merge Buttons*

![Tag-Suggestions Queue](images/screenshots/tag-suggestions-queue.png)

Wenn die KI **neue Tag-Namen** vorschlägt, landen diese in der Queue.

**Zugriff:** **💡 Tag-Vorschläge** in der Navigation

**Actions:**
- **✅ Approve**: Erstellt den Tag und weist ihn zu
- **❌ Reject**: Verwirft den Vorschlag
- **🔀 Merge**: Ordnet zu existierendem Tag zu
- **Batch**: Alle auf einmal annehmen/ablehnen

**Zwei Einstellungen:**

| Setting | Was es macht | Default |
|---------|--------------|---------|
| **💡 Tag-Vorschläge für neue Tags** | KI darf neue Tag-Namen vorschlagen | OFF |
| **⚡ Automatische Tag-Zuweisung** | Bestehende Tags bei ≥80% automatisch zuweisen | OFF |

> ⚙️ **Einstellungen ändern:** Klicke auf ⚙️ Button rechts oben auf `/tag-suggestions` Seite

**Kombinationen:**

| Queue | Auto | Verhalten |
|-------|------|-----------|
| OFF | OFF | Nur manuelle Vorschläge in Email-Detail |
| OFF | ON | Bestehende Tags automatisch, keine neuen Vorschläge |
| ON | OFF | Queue für neue Tags, manuelle Zuweisung |
| ON | ON | Queue + Auto-Assignment (volle KI-Automation) |

**Lernen aus deinem Verhalten:**
- Je mehr Emails du manuell taggst, desto besser werden die Vorschläge
- Das System lernt: "Emails über Rechnungen bekommen meist den Tag 'Finanzen'"
- Nach ~5-10 manuellen Zuweisungen pro Tag werden Vorschläge sehr genau
- **Negative Feedback** verhindert false-positives

> 💡 **Tipp:** Starte mit wenigen Tags, tagge konsequent, und nutze × Button für unpassende Vorschläge!

---

## 7. Auto-Rules (Automatische Regeln)

> **📸 Screenshot:** Auto-Rules Seite (/rules)  
> *Zeige: Regel-Liste mit Bedingungen und Aktionen, "Neue Regel" Button*

![Auto-Rules Verwaltung](images/screenshots/auto-rules.png)

Über **⚡ Auto-Rules** in der Navigation erreichst du die Regel-Verwaltung.

### 7.1 Was sind Auto-Rules?

Auto-Rules führen **automatisch Aktionen** aus, wenn eine Email bestimmte Bedingungen erfüllt. Sie werden nach jedem Email-Abruf angewendet.

**Beispiel:** "Wenn der Absender 'newsletter' enthält, dann Tag 'Newsletter' zuweisen und als gelesen markieren."

### 7.2 Regel erstellen

> **📸 Screenshot:** "Neue Regel" Modal mit Bedingungen und Aktionen  
> *Zeige: Name, Bedingungen-Liste, Match-Mode, Aktionen-Liste*

![Neue Regel erstellen](images/screenshots/new-rule-modal.png)

1. Klicke auf **"➕ Neue Regel"**
2. Gib einen **Namen** für die Regel ein
3. Definiere **Bedingungen** (mindestens eine)
4. Wähle den **Match-Mode** (Alle/Eine)
5. Definiere **Aktionen** (mindestens eine)
6. Klicke auf **"Speichern"**

### 7.3 Verfügbare Bedingungen

| Kategorie | Bedingung | Beschreibung |
|-----------|-----------|--------------|
| **Absender** | equals | Exakte Übereinstimmung |
| | contains | Enthält Text |
| | not_contains | Enthält nicht |
| | domain | Domain-Match (z.B. "@newsletter.com") |
| **Betreff** | equals | Exakte Übereinstimmung |
| | contains | Enthält Text |
| | not_contains | Enthält nicht |
| | regex | Regulärer Ausdruck |
| **Inhalt** | contains | Body enthält Text |
| | not_contains | Body enthält nicht |
| | regex | Regulärer Ausdruck |
| **Anhänge** | has_attachment | Hat Anhänge (ja/nein) |
| **Ordner** | folder_equals | Bestimmter IMAP-Ordner |
| **Tags** | has_tag | Hat bestimmten Tag |
| | not_has_tag | Hat Tag nicht |
| **KI** | ai_suggested_tag | KI schlägt Tag vor (mit Confidence) |

**Match-Mode:**
- **ALLE** (AND): Alle Bedingungen müssen erfüllt sein
- **EINE** (OR): Mindestens eine Bedingung muss erfüllt sein

### 7.4 Verfügbare Aktionen

| Aktion | Beschreibung |
|--------|--------------|
| **📁 In Ordner verschieben** | IMAP MOVE zu anderem Ordner |
| **👁️ Als gelesen markieren** | Setzt das Seen-Flag |
| **🚩 Flaggen** | Markiert als wichtig |
| **🏷️ Tag zuweisen** | Weist einen Tag zu (mit Farb-Anzeige) |
| **⬆️⬇️ Priorität setzen** | High oder Low |
| **🗑️ Löschen** | Soft-Delete |
| **⏹️ Verarbeitung stoppen** | Keine weiteren Regeln anwenden |

### 7.5 Vorgefertigte Templates

> **📸 Screenshot:** Template-Dropdown  
> *Zeige: Dropdown mit 4 Templates*

![Rule Templates](images/screenshots/rule-templates.png)

Für häufige Anwendungsfälle gibt es Templates:

| Template | Bedingungen | Aktionen |
|----------|-------------|----------|
| **Newsletter archivieren** | Domain enthält "newsletter" | In "Archive" verschieben, als gelesen |
| **Spam löschen** | Absender enthält "spam" | In Papierkorb |
| **Wichtige Absender** | Absender = chef@firma.de | Flaggen, Priorität High |
| **Anhänge archivieren** | Hat Anhänge | In "Attachments" verschieben |

### 7.6 Regel testen (Dry-Run)

> **📸 Screenshot:** Dry-Run Ergebnis  
> *Zeige: Liste der betroffenen Emails ohne Änderungen*

![Dry-Run Ergebnis](images/screenshots/dry-run.png)

Bevor eine Regel scharf geschaltet wird, kannst du sie testen:

1. Öffne die Regel
2. Klicke auf **"🧪 Testen (Dry-Run)"**
3. Sieh, welche Emails betroffen wären
4. Keine Änderungen werden durchgeführt

### 7.7 Statistiken

Jede Regel zeigt:
- **Ausgeführt:** Wie oft wurde die Regel angewendet?
- **Zuletzt:** Wann wurde sie zuletzt ausgelöst?

---

## 8. Antwort-Stile

> **📸 Screenshot:** Antwort-Stile Einstellungsseite (/reply-styles)  
> *Zeige: Globale Einstellungen Card + Stil-Tabs (Formell, Freundlich, Kurz, Ablehnung)*

![Antwort-Stile](images/screenshots/reply-styles.png)

Über **Einstellungen → Antwort-Stile** kannst du anpassen, wie die KI Antwort-Entwürfe generiert.

### 8.1 Globale Einstellungen

Diese Einstellungen gelten als Standard für alle Antwort-Stile:

| Feld | Beschreibung | Beispiel |
|------|--------------|----------|
| **Anrede-Form** | Automatisch, Du oder Sie | `auto` (erkennt aus Email) |
| **Standard-Anrede** | Wie beginnt die Antwort? | `Liebe/r`, `Guten Tag` |
| **Grussformel** | Wie endet die Antwort? | `Beste Grüsse`, `Herzliche Grüsse` |
| **Signatur anhängen** | Checkbox + Textarea | Mehrzeilig möglich |
| **Zusätzliche Anweisungen** | Spezielle Vorgaben für die KI | "Wir duzen uns in der Firma" |

**Beispiel Signatur:**
```
Mike Weber
Technischer Support
Firma GmbH
+41 79 123 45 67
```

> 💡 **Tipp:** Leere Felder = KI entscheidet automatisch basierend auf dem Email-Inhalt.

### 8.2 Stil-spezifische Anpassungen

Die 4 Antwort-Stile können individuell überschrieben werden:

| Stil | Standard-Verhalten | Typische Anpassungen |
|------|-------------------|----------------------|
| **📜 Formell** | Höflich, distanziert, Sie-Form | "Sehr geehrte/r", "Mit freundlichen Grüssen" |
| **😊 Freundlich** | Warmherzig, persönlich, Du-Form | "Liebe/r", "Herzliche Grüsse" |
| **⚡ Kurz** | Prägnant, direkt, ohne Floskeln | "Hallo", "Grüsse" |
| **❌ Ablehnung** | Höflich ablehnen mit Alternative | "Leider müssen wir ablehnen, aber..." |

**Wann überschreiben?**
- Du möchtest für **formelle** Emails immer "Sie" verwenden
- Du möchtest für **freundliche** Emails eine andere Signatur
- Du möchtest bei **Ablehnungen** spezielle Anweisungen ("Immer Alternative anbieten")

> **📸 Screenshot:** Stil-spezifischer Tab (z.B. "Formell")  
> *Zeige: Info-Box "Leere Felder übernehmen Global" + Formular-Felder + "Überschreibungen löschen" Button*

![Stil-spezifische Einstellungen](images/screenshots/reply-styles-formal.png)

### 8.3 Merge-Logik verstehen

Die KI kombiniert deine Einstellungen in 3 Stufen:

```
┌─────────────────────────────────────────────┐
│ 1️⃣ SYSTEM DEFAULTS                          │
│    (Eingebaute Standard-Prompts)            │
└─────────────────────────────────────────────┘
                   ↓ überschrieben von
┌─────────────────────────────────────────────┐
│ 2️⃣ GLOBAL SETTINGS                          │
│    (Deine globalen Einstellungen)           │
└─────────────────────────────────────────────┘
                   ↓ überschrieben von
┌─────────────────────────────────────────────┐
│ 3️⃣ STYLE-SPECIFIC OVERRIDES                │
│    (Nur gefüllte Felder des gewählten Stils)│
└─────────────────────────────────────────────┘
```

**Beispiel:**

| Feld | Global | Formell (Override) | Ergebnis |
|------|--------|-------------------|----------|
| Anrede-Form | `auto` | `sie` | **sie** (überschrieben) |
| Anrede | `Hallo` | *(leer)* | **Hallo** (von Global) |
| Grussformel | `Beste Grüsse` | `Mit freundlichen Grüssen` | **Mit freundlichen Grüssen** (überschrieben) |
| Signatur | Mike | *(leer)* | **Mike** (von Global) |

### 8.4 Preview-Funktion

> **📸 Screenshot:** Preview-Bereich mit Muster-Antwort  
> *Zeige: Textarea mit generiertem Preview-Text*

![Antwort-Preview](images/screenshots/reply-styles-preview.png)

Die Preview zeigt dir sofort, wie eine Antwort mit deinen aktuellen Einstellungen aussieht:

1. Wähle einen Stil-Tab (z.B. "Freundlich")
2. Ändere Einstellungen
3. Klicke auf **"Aktualisieren"** oder warte kurz
4. Preview wird automatisch aktualisiert

**Preview-Beispiel:**
```
Liebe/r Max Mustermann,

[Ihr Antwort-Text wird hier erscheinen...]

Herzliche Grüsse
Mike Weber
Technischer Support
```

### 8.5 Änderungen speichern

1. **"Alle Änderungen speichern"** – Speichert globale + aktuelle Stil-Einstellungen
2. **"Überschreibungen löschen"** – Setzt Stil-spezifische Änderungen zurück auf Global
3. **"Auf Standard zurücksetzen"** – Löscht ALLE Anpassungen (Global + alle Stile)

> ⚠️ Alle Signatur-Texte und Custom Instructions werden **verschlüsselt** in der Datenbank gespeichert (Zero-Knowledge).

---

## 9. KI-Priorisierung

> **🎯 Hybrid Pipeline mit spaCy NLP + Ensemble Learning**

Die KI-Priorisierung nutzt eine hochentwickelte **Hybrid-Pipeline**, die deutsche Emails mit **80% NLP (spaCy)** und **20% strategischen Keywords** analysiert. Das System lernt aus deinen Korrekturen durch **Ensemble Learning** und passt sich an deinen Workflow an.

### 9.1 Was ist KI-Priorisierung?

**KI-Priorisierung = spaCy Hybrid Pipeline** kombiniert:
- **7 NLP-Detektoren** für linguistische Analyse
- **12 Keyword-Sets** mit 80 strategischen Begriffen
- **Ensemble Learning** (spaCy + SGD Regression) mit dynamischen Gewichten
- **Account-spezifische Konfiguration** für individuelle Anpassungen

**Zugriff:** Klicke auf **🎯 KI-Priorisierung** in der Navigation

> **📸 Screenshot:** KI-Priorisierung Konfigurations-Interface  
> *Zeige: 4 Tabs (VIP, Keywords, Scoring, Domains) mit Account-Selector*

![KI-Priorisierung](images/screenshots/phase-y-config.png)

### 9.2 Email-Anonymisierung (DSGVO-konform)

> **Neue Feature seit Version 1.3.0**

Wenn du Cloud-AI-Provider (OpenAI, Anthropic, Mistral) nutzt, werden personenbezogene Daten (PII) übertragen. Mit der **Email-Anonymisierung** kannst du diese Daten vor der Übertragung automatisch entfernen.

**Wie funktioniert es?**

Das System nutzt **spaCy Named Entity Recognition (NER)** mit dem deutschen Modell `de_core_news_sm`, um personenbezogene Informationen zu erkennen und zu ersetzen:

- **Personen** (PER): `Hans Müller` → `[PERSON_1]`
- **Organisationen** (ORG): `Microsoft GmbH` → `[ORG_1]`
- **Orte** (LOC): `Berlin` → `[LOC_1]`
- **Emails/Telefon** (Regex): `hans@test.de` → `[EMAIL_1]`

**Sanitization-Levels:**

| Level | Beschreibung | Entfernt |
|-------|--------------|----------|
| 🔹 **Regex** | Schnell (ohne spaCy) | Emails, Telefonnummern, URLs |
| 🔸 **Light** | spaCy NER Basis | Regex + PER (Personen) |
| 🔺 **Full** | spaCy NER Komplett | Regex + PER + ORG + LOC |

**Aktivierung:**

1. Gehe zu **📬 Absender & Abruf** (`/whitelist`)
2. Wähle deinen Account
3. Aktiviere **"🛡️ Mit Spacy anonymisieren"**
4. Wähle Sanitization-Level (empfohlen: **Full**)
5. Speichern

**Hierarchische Analyse-Modi:**

Das System wählt automatisch den passenden Modus basierend auf deinen Einstellungen:

| Modus | Beschreibung | Badge |
|-------|--------------|-------|
| **spacy_booster** | UrgencyBooster auf Original-Daten (lokal, kein LLM) | ⚡ Spacy Booster |
| **llm_anon** | LLM-Analyse auf anonymisierten Daten (Privacy) | 🤖 AI-Anon (Provider) |
| **llm_original** | LLM-Analyse auf Original-Daten (beste Qualität) | 🤖 AI-Orig (Provider) |
| **none** | Nur Embeddings, keine Bewertung | ❌ Keine AI |

**Beispiel-Kombination:**
- ✅ AI-Analyse AN + 🛡️ Anonymisierung AN = **llm_anon** (Cloud-AI mit Privacy)
- ✅ AI-Analyse AN + 🛡️ Anonymisierung AUS + ⚡ Booster AN = **spacy_booster** (lokal, schnell)

**Anonymisierte Version ansehen:**

Nach der Anonymisierung findest du in der Email-Detail-Ansicht einen neuen Tab:

- **🛡️ Anonymisiert** (33 Entities erkannt, Level 3)

Hier siehst du, wie die Email an die Cloud-AI übertragen wurde.

> 💡 **Tipp:** Anonymisierung + Cloud-AI ist ideal für sensible Business-Emails. UrgencyBooster (lokal) ist besser für Newsletter/Marketing.

**Performance:**
- Erste Analyse: ~1200ms (Modell-Loading)
- Folgende Emails: ~10-15ms pro Email
- Modell wird nur bei Bedarf geladen (kein Startup-Overhead)

> ⚠️ **Wichtig:** Anonymisierung ist unabhängig vom UrgencyBooster. Du kannst beide gleichzeitig aktivieren – das System wählt den passenden Modus automatisch.

### 9.3 VIP-Absender konfigurieren

> **Tab 1: VIP-Absender**

VIP-Absender bekommen automatisch einen **Boost** auf Wichtigkeit/Dringlichkeit.

**Wichtigkeits-Stufen:**

| Stufe | Boost | Verwendung |
|-------|-------|------------|
| 1️⃣ **Low** | +0.5 | Weniger wichtige Kontakte |
| 2️⃣ **Medium** | +1.0 | Normale VIPs (z.B. Team-Leads) |
| 3️⃣ **High** | +1.5 | Sehr wichtige Kontakte (z.B. C-Level) |
| 4️⃣ **Critical** | +2.0 | Kritisch (z.B. CEO, Key Accounts) |

**VIP hinzufügen:**
1. Wähle Account aus Dropdown
2. Email-Adresse eingeben (z.B. `chef@firma.de`)
3. Wichtigkeits-Stufe wählen
4. Optional: Notiz hinzufügen
5. Klick auf **"➕ Hinzufügen"**

**Beispiel:**
```
Email: ceo@firma.de
Wichtigkeit: Critical (+2.0)
Notiz: CEO – immer vorrangig behandeln
```

> 💡 **Tipp:** VIP-Status gilt nur für den ausgewählten Account. Für multi-account VIPs: Mehrfach hinzufügen.

### 9.4 Keywords anpassen

> **Tab 2: Keywords**

Das System nutzt **12 vordefinierte Keyword-Sets** mit insgesamt **80 strategischen Begriffen**.

**Standard Keyword-Sets:**

| Set | Beispiel-Keywords | Verwendung |
|-----|-------------------|------------|
| **imperative_verbs** | bitte, müssen, sollen, erledigen | Handlungsaufforderungen |
| **urgency_time** | asap, dringend, sofort, eilig | Zeitdruck-Signale |
| **deadline_markers** | Deadline, Frist, bis, spätestens | Fristenrelevanz |
| **follow_up_signals** | Erinnerung, Rückfrage, nachhaken | Follow-up Bedarf |
| **question_words** | warum, wie, was, wann | Rückfragen |
| **negation_terms** | nicht, kein, leider, ohne | Problemsignale |
| **escalation_words** | eskalation, Chef, kritisch | Eskalationsrelevanz |
| **confidential_markers** | vertraulich, geheim, NDA | Vertraulichkeit |
| **contract_terms** | Vertrag, Angebot, Kündigung | Rechtl. Relevanz |
| **financial_words** | Rechnung, Zahlung, Budget | Finanzielle Relevanz |
| **meeting_terms** | Termin, Meeting, Call | Terminrelevanz |
| **sender_hierarchy** | Geschäftsführer, Vorstand, Leitung | Absender-Wichtigkeit |

**Keywords bearbeiten:**
1. Klicke auf **"📝 Keywords bearbeiten"**
2. Ändere Keywords (kommagetrennt): `dringend, asap, sofort, eilig`
3. Klicke auf **"💾 Speichern"**
4. Oder: **"🔄 Zurücksetzen"** für Standard-Keywords

**Beispiel-Anpassung:**
```
Ursprünglich (urgency_time): asap, dringend, sofort, eilig
Angepasst: asap, dringend, sofort, eilig, heute noch, morgen früh
```

> ⚠️ **Achtung:** Keywords sind **account-spezifisch**. Änderungen gelten nur für den aktuellen Account.

### 9.5 Scoring-Gewichte

> **Tab 3: Scoring**

Hier passt du an, wie stark einzelne Detektoren die finale Bewertung beeinflussen.

**Scoring-Struktur:**

```
Wichtigkeit = (Imperative × W1 + Keywords × W2 + VIP × W3 + ... ) × Base-Weight
Dringlichkeit = (Deadline × W1 + Urgency × W2 + Question × W3 + ... ) × Base-Weight
```

**Verfügbare Gewichte:**

| Gewicht | Range | Standard | Beschreibung |
|---------|-------|----------|--------------|
| **imperative_weight** | 0.0-5.0 | 1.0 | Handlungsaufforderungen (machen, erledigen) |
| **deadline_weight** | 0.0-5.0 | 2.0 | NER-basierte Datums-Erkennung |
| **keyword_urgency_weight** | 0.0-5.0 | 1.5 | urgency_time Keywords |
| **keyword_importance_weight** | 0.0-5.0 | 1.0 | confidential/contract/financial Keywords |
| **question_weight** | 0.0-5.0 | 0.8 | Rückfragen (W-Fragen) |
| **negation_weight** | 0.0-5.0 | 0.6 | Verneinungen/Probleme |
| **vip_boost_multiplier** | 0.0-3.0 | 1.5 | VIP-Absender Multiplikator |
| **internal_reduction** | 0.0-1.0 | 0.3 | Interne Emails Dämpfung (30%) |

**Gewichte anpassen:**
1. Ziehe Slider für gewünschtes Gewicht
2. Klicke auf **"💾 Scoring speichern"**
3. Oder: **"📥 Standard laden"** für Default-Werte

**Beispiel-Anpassung:**
```
Szenario: Deadlines sind für dich extrem wichtig

Standard: deadline_weight = 2.0
Angepasst: deadline_weight = 4.0
→ Emails mit Deadlines bekommen doppelten Boost!
```

> 💡 **Tipp:** Starte mit Standard-Werten und passe nach einigen Wochen an, wenn du Muster erkennst.

### 9.5 User-Domains (Intern/Extern)

> **Tab 4: Domains**

Definiere, welche Email-Domains als **intern** gelten. Interne Emails bekommen **30% Dämpfung** (konfigurierbar via `internal_reduction`).

**Domain hinzufügen:**
1. Wähle Account
2. Domain eingeben (z.B. `firma.de`)
3. Klicke auf **"➕ Hinzufügen"**

**Beispiel:**
```
Domains: firma.de, team.firma.de, internal.firma.de
→ Alle Emails von diesen Domains = Intern
→ Wichtigkeit/Dringlichkeit × 0.7 (wenn internal_reduction = 0.3)
```

**Warum Dämpfung?**
- Interne Emails sind oft weniger zeitkritisch
- Externe Kunden/Partner haben Priorität
- Anpassbar über `internal_reduction` Slider (Tab 3)

> ⚠️ **Subdomain-Matching:** `firma.de` matched auch `mail.firma.de`, `team.firma.de` usw.

### 9.6 Ensemble Learning

**Was ist Ensemble Learning?**

Das System kombiniert **zwei KI-Modelle**:
1. **spaCy Hybrid Pipeline** (NLP + Keywords)
2. **SGD Regression** (lernt aus deinen Korrekturen)

**Dynamische Gewichte:**

| Korrektur-Anzahl | spaCy Gewicht | SGD Gewicht | Phase |
|------------------|---------------|-------------|-------|
| **< 20** | 100% | 0% | 🆕 Kaltstart (nur spaCy) |
| **20-50** | 30% | 70% | 📈 Übergangsphase |
| **> 50** | 15% | 85% | 🧠 Voll trainiert |

**Wie funktioniert's?**
1. Du korrigierst eine Email-Bewertung (z.B. Wichtigkeit 3 → 5)
2. SGD lernt: "Bei dieser Art Email: höher bewerten!"
3. Nächste ähnliche Email: SGD schlägt besseren Wert vor
4. System kombiniert spaCy + SGD = **genauere Vorhersage**

**Monitoring:**
- Jede Bewertung speichert `spacy_details` (JSON mit Detector-Scores)
- Jede Bewertung speichert `ensemble_stats` (Gewichte, Modell-Beiträge)
- In Email-Detail: Siehst du spaCy vs. SGD Beiträge

**Beispiel:**
```json
{
  "wichtigkeit": 4,
  "dringlichkeit": 5,
  "spacy_contribution": {"wichtigkeit": 0.6, "dringlichkeit": 1.0},
  "sgd_contribution": {"wichtigkeit": 3.4, "dringlichkeit": 4.0},
  "weights": {"spacy_weight": 0.15, "sgd_weight": 0.85},
  "correction_count": 73
}
```

> 🎯 **Performance-Ziel:** < 500ms Analyse-Zeit (inkl. spaCy NLP + Embedding)

---

## 10. IMAP-Diagnostics

> **📸 Screenshot:** IMAP-Diagnostics Dashboard (/imap-diagnostics)  
> *Zeige: Account-Auswahl, Test-Buttons, Ergebnis-Bereich*

![IMAP-Diagnostics](images/screenshots/imap-diagnostics.png)

Unter **🔧 IMAP-Test** findest du Diagnose-Tools für deine Mail-Accounts.

### 10.1 Verfügbare Tests

| Test | Beschreibung |
|------|--------------|
| **🔌 Verbindungstest** | Prüft IMAP-Server-Erreichbarkeit und Login |
| **📁 Ordner-Liste** | Zeigt alle IMAP-Ordner mit Email-Anzahl |
| **🔄 DB-Sync-Check** | Vergleicht lokale DB mit IMAP-Server |
| **📊 Mail-Count** | Zählt Emails pro Ordner (Remote vs. Lokal) |

### 10.2 DB-Sync-Check verstehen

> **📸 Screenshot:** Sync-Check Ergebnis mit Ordner-Details  
> *Zeige: Ordner-Liste, IMAP vs DB Vergleich, Delta-Anzeige*

![DB-Sync-Check](images/screenshots/sync-check.png)

Der Sync-Check zeigt für jeden Ordner:

| Spalte | Bedeutung |
|--------|-----------|
| **IMAP** | Anzahl Emails auf dem Server |
| **DB** | Anzahl Emails in lokaler Datenbank |
| **Delta** | Differenz (positiv = fehlen lokal) |
| **Status** | 🟢 Sync / 🟡 Delta / 🔴 Problem |

**Status-Farben:**
- 🟢 **Grün:** Lokal und Server sind synchron
- 🟡 **Gelb:** Delta vorhanden (Emails fehlen lokal)
- 🔴 **Rot:** UIDVALIDITY-Mismatch (Ordner wurde auf Server neu erstellt)

### 10.3 Multi-Folder Ansicht

> **📸 Screenshot:** Multi-Folder Übersicht mit aufgeklapptem Detail  
> *Zeige: Ordner-Tree mit Details zu UIDs und Flags*

![Multi-Folder Ansicht](images/screenshots/multi-folder-view.png)

Klicke auf einen Ordner, um Details zu sehen:
- Einzelne Email-UIDs
- IMAP-Flags vs. DB-Status
- Mismatch-Highlighting

> 💡 **Tipp:** Bei großen Deltas nutze "Jetzt abrufen" in den Einstellungen, um fehlende Emails zu synchronisieren.

---

## 11. Einstellungen

> **📸 Screenshot:** Einstellungen-Seite komplett (settings.html)  
> *Zeige: Alle Sektionen (Mail-Accounts, KI, SMTP, Sicherheit)*

![Einstellungen](images/screenshots/settings.png)

### 11.1 Mail-Accounts verwalten

> **📸 Screenshot:** Mail-Account Liste in Einstellungen  
> *Zeige: Account-Karten mit Status, Bearbeiten/Löschen Buttons*

![Mail-Account Liste](images/screenshots/settings-accounts.png)

**Account-Tabelle verstehen:**

| Spalte | Bedeutung |
|--------|-----------|
| **ID** | Eindeutige Account-Nummer (wichtig für CLI & Fetch-Filter) |
| **Name** | Dein Account-Name (z.B. "martina") |
| **Server** | IMAP-Server-Adresse |
| **Port** | IMAP-Port (Standard: 993) |
| **Benutzer** | Email-Adresse des Accounts |
| **Status** | Aktiv (grün) oder Inaktiv (grau) + **Status-Badges** |

**Neue Status-Badges (Version 1.3.0):**

Die Einstellungen zeigen jetzt für jeden Account **Status-Badges**, die die aktuellen Analyse-Einstellungen anzeigen:

| Badge | Bedeutung | Konfiguration |
|-------|-----------|---------------|
| 🛡️ **Anon** | Anonymisierung aktiv (PII-Entfernung vor Cloud-AI) | `/whitelist` → "Mit Spacy anonymisieren" |
| ⚡ **Booster** | UrgencyBooster aktiv (spaCy NLP auf Original) | `/whitelist` → "UrgencyBooster aktivieren" |
| 🤖 **AI-Anon (Provider)** | LLM-Analyse auf anonymisierten Daten | Automatisch wenn Anon + AI AN |
| 🤖 **AI-Orig (Provider)** | LLM-Analyse auf Original-Daten | Automatisch wenn AI AN, Anon AUS |
| ❌ **Keine AI** | Nur Embeddings, keine Bewertung | AI-Analyse AUS |

**Beispiel-Kombinationen:**

| Einstellungen | Effekt | Badge |
|---------------|--------|-------|
| ✅ AI AN + 🛡️ Anon AN + ⚡ Booster AUS | LLM auf anonymisierten Daten (Privacy) | 🛡️ Anon, 🤖 AI-Anon (claude-3-5-sonnet) |
| ✅ AI AN + 🛡️ Anon AUS + ⚡ Booster AN | spaCy Booster auf Original (lokal, schnell) | ⚡ Booster |
| ✅ AI AN + 🛡️ Anon AUS + ⚡ Booster AUS | LLM auf Original (beste Qualität) | 🤖 AI-Orig (claude-3-5-sonnet) |
| ❌ AI AUS | Nur Embeddings (manuelles Tagging) | ❌ Keine AI |

> 💡 **Tipp:** Klicke auf die Badges, um direkt zur `/whitelist`-Konfiguration zu gelangen!

> 💡 **Anwendungsfall:**
> - **Business (sensibel):** 🛡️ Anon + 🤖 AI-Anon → Keine PII an Cloud
> - **Newsletter:** ❌ Keine AI → Manuelles Tagging für besseres ML-Learning
> - **VIP-Accounts:** ⚡ Booster → Schnelle Analyse für Trusted Senders

> 💡 **Tipp:** Die **Account-ID** brauchst du für:
> - CLI-Befehle (`scripts/list_accounts.py`)
> - Fetch-Filter (nur bestimmte Accounts abrufen)
> - Bulk-Operations (später)

**Account bearbeiten:**
1. Klicke auf **"Bearbeiten"** beim gewünschten Account
2. Ändere Server, Port oder Zugangsdaten
3. **🆕 Account-Signatur konfigurieren** (Optional):
   - Aktiviere **"Account-spezifische Signatur verwenden"**
   - Gib deine Signatur ein (mehrzeilig möglich)
   - Diese Signatur wird automatisch bei Antworten für Emails von diesem Account verwendet
   - Priorität: Account-Signatur > User-Style-Signatur > Globale Signatur
4. Klicke auf **"Speichern"**

> 💡 **Anwendungsfall Account-Signaturen:**
> - **Geschäftlich:** `max@firma.ch` → "Mit freundlichen Grüssen, Max Mustermann, IT-Abteilung"
> - **Privat:** `max@gmail.com` → "Liebe Grüsse, Max"
> - **Uni:** `m.mustermann@students.example.com` → "Beste Grüsse, Max Mustermann, Student Informatik"

**Account löschen:**
1. Klicke auf **"Löschen"**
2. Bestätige im Dialog

> ⚠️ Beim Löschen werden alle Emails dieses Accounts aus der lokalen Datenbank entfernt!

**Emails abrufen:**
- **Manuell:** Klicke auf **"Jetzt abrufen"** beim Account
- **Automatisch:** Ein Hintergrund-Job prüft regelmäßig (alle 15 Min.)
- **Fetch-Filter:** Account-spezifische Filter (Ordner, Datum, UNSEEN) für selektiven Abruf

> **📸 Screenshot:** Email-Abruf Progress-Modal  
> *Zeige: Fortschrittsbalken, "X von Y Emails verarbeitet"*

![Email-Abruf Progress](images/screenshots/fetch-progress.png)

**Performance-Optimierungen:**
- ✅ **Smart SINCE-Search**: Nur ausgewählte Ordner werden für Datumsfilter durchsucht
- ✅ **30s Cache**: Wiederholte Zugriffe auf Ordner-Counts sind instant
- ✅ **Request-Abbruch**: Account-Wechsel bricht laufende Requests ab
- ⚡ **Beispiel**: 132 Ordner in ~7-8s statt 120s+ (94% schneller)

> 💡 **Multi-Account Setup**: Bei mehreren Accounts mit vielen Ordnern (>100) verhindert die App automatisch Timeouts durch intelligentes Caching und selektives Laden.

### 11.2 SMTP konfigurieren (Email-Versand)

> **📸 Screenshot:** SMTP-Einstellungen im Account-Formular  
> *Zeige: SMTP-Server, Port, Verschlüsselung, optionale separate Credentials*

![SMTP-Konfiguration](images/screenshots/smtp-settings.png)

Um Emails direkt aus der App zu senden, muss SMTP konfiguriert sein:

**Bei Account-Erstellung oder -Bearbeitung:**

| Feld | Beispiel (GMX) | Beschreibung |
|------|----------------|--------------|
| SMTP-Server | smtp.gmx.net | Ausgehender Mail-Server |
| SMTP-Port | 587 | Standard: 587 (STARTTLS) oder 465 (SSL) |
| SMTP-Verschlüsselung | STARTTLS | STARTTLS oder SSL |
| SMTP-Username | (optional) | Falls anders als IMAP |
| SMTP-Passwort | (optional) | Falls anders als IMAP |

> 💡 **Tipp:** Bei den meisten Providern (GMX, Gmail, etc.) sind SMTP-Credentials identisch mit IMAP. Du musst sie dann nicht separat eingeben.

**SMTP-Verbindung testen:**
1. Gehe zu den Account-Einstellungen
2. Klicke auf **"🔌 SMTP testen"**
3. Bei Erfolg: "✅ SMTP-Verbindung erfolgreich"

### 11.3 KI-Provider konfigurieren

> **📸 Screenshot:** KI-Einstellungen Sektion  
> *Zeige: Provider-Dropdown, 3 Modell-Auswahlen*

![KI-Provider Einstellungen](images/screenshots/ki-settings.png)

**Unterstützte Provider:**

| Provider | Beschreibung | Kosten |
|----------|--------------|--------|
| **Ollama (lokal)** | Läuft auf deinem Server | Kostenlos |
| **OpenAI** | GPT-Modelle via API | Pay-per-use |
| **Anthropic** | Claude via API | Pay-per-use |
| **Mistral** | Mistral via API | Pay-per-use |

**Drei-Modell-System:**

| Einstellung | Zweck | Empfehlung |
|-------------|-------|------------|
| **Embedding Model** | Für semantische Suche & Tag-Vorschläge | all-minilm:22m (schnell, klein) |
| **Base Model** | Für erste Email-Analyse | llama3.2:1b (schnell) |
| **Optimize Model** | Für tiefe Analyse ("Optimieren") | llama3.2:3b oder claude-haiku |

> 💡 **Empfehlung für Heimserver:** Ollama mit all-minilm:22m für Embeddings und llama3.2 für Analyse. Kostenlos und privat!

#### Hardware-Hinweise: CPU vs GPU

Die **richtige Modellwahl hängt von deiner Hardware ab:**

**Mit dedizierter GPU (CUDA - z.B. NVIDIA RTX):**
- ✅ Größere Modelle nutzbar (llama3.1:8b, mistral:7b)
- ✅ Sehr schnell (<1 Sek pro Email)
- ✅ Beste Out-of-the-Box Qualität

**Nur CPU (ohne dedizierte GPU):**
- ⚠️ Kleine Modelle empfohlen (llama3.2:1b, max 3b)
- ⚠️ Langsamer (5-10 Min pro Email bei 1b)
- ✅ **Learning-System gleicht schwächere Modelle aus!**

**💡 CPU-only Strategie (besonders wichtig!):**

Ein **llama3.2:1b mit Learning** liefert nach 1-2 Wochen bessere Ergebnisse als ein **llama3.1:8b ohne Learning**:

| Zeitraum | Similarity | False-Positives | Zeitaufwand |
|----------|------------|-----------------|-------------|
| **Start (ohne Learning)** | 15-25% | 20-30% | - |
| **1 Woche (15-20 Tags)** | 75-85% | 10-15% | ~3 Min/Tag |
| **2 Wochen (30-40 Tags + Rejects)** | 90-95% | 5-8% | ~5 Min/Tag |

**Was du tun solltest:**
1. **Taggen:** 3-5 Emails pro Tag manuell taggen
2. **Rejecting:** Unpassende Vorschläge mit × Button ablehnen (Negative Feedback)
3. **Geduld:** Nach 1-2 Wochen kennt das System deine Präferenzen perfekt

**Alternative für CPU-only:**
- **Hybrid-Ansatz:** Embedding lokal, Base/Optimize Cloud (GPT-4o-mini/Claude)
- Vorteil: Schnell und präzise, Embeddings bleiben lokal (Privacy)

> 📘 **Detaillierte Modell-Empfehlungen:** Siehe [KI_MODELL_EMPFEHLUNGEN.md](KI_MODELL_EMPFEHLUNGEN.md) für Performance-Benchmarks, Hardware-Richtwerte und Learning-Strategien.

---

### 11.4 Absender & Abruf (Trusted Senders + AI-Control)

**Phase X + X.3** erlaubt dir, pro Mail-Account zu steuern, welche AI-Features beim Abrufen neuer Mails verwendet werden.

**Navigation:** 📬 **Absender & Abruf** (Menü) oder **Settings** → **Mail-Accounts**

#### Warum Account-Level Kontrolle?

Nach Analyse der Performance:
- Rule-basierte Systeme (spaCy UrgencyBooster) funktionieren nur bei **expliziten Signalen** (Rechnungen, Deadlines, Geldbeträge)
- Für **Newsletter/Marketing-Emails** mit subtilen Mustern ist **ML-Learning aus User-Korrekturen** überlegen
- Unterschiedliche Accounts haben unterschiedliche Bedürfnisse:
  - **Business**: Automatische Priorisierung gewünscht
  - **Newsletter**: Manuelles Tagging für besseres Learning bevorzugt

#### Zwei unabhängige Toggles pro Account:

**✅ AI-Analyse beim Abruf**
- **Aktiviert**: Komplette LLM-Analyse (Dringlichkeit, Wichtigkeit, Kategorie, Summary, Tags)
- **Deaktiviert**: Nur Embedding erstellen, keine Bewertung → Manuelles Tagging erforderlich
- **Vorteil deaktiviert**: Keine AI-Halluzinationen, ML-Classifier lernt nur aus echten User-Entscheidungen
- **Nachteil deaktiviert**: Alle Emails müssen manuell klassifiziert werden

**✅ UrgencyBooster (spaCy)**
- **Aktiviert**: Schnelle Entity-basierte Analyse für Trusted Senders (100-300ms statt 2-3s LLM)
- **Deaktiviert**: Nur LLM-Analyse, langsamer aber universell einsetzbar
- **Vorteil aktiviert**: Performance-Boost für whitelistete Absender
- **Nachteil aktiviert**: Funktioniert nur bei expliziten Signalen, versagt bei subtilen Mustern

#### Empfohlene Konfigurationen:

| Account-Typ | AI-Analyse | UrgencyBooster | Begründung |
|-------------|------------|----------------|------------|
| **📧 Newsletter** (GMX, Marketing) | ⭕ AUS | ⭕ AUS | Manuelles Tagging → ML lernt subtile Muster → Automatische Verbesserung |
| **💼 Business** (Arbeit, Uni) | ✅ AN | ✅ AN | Trusted Senders profitieren von spaCy, andere von LLM |
| **🔀 Hybrid** | ✅ AN | ⭕ AUS | Nur LLM ohne spaCy-Overhead (langsamer, aber präziser) |
| **🎓 Pure ML** | ⭕ AUS | ⭕ AUS | Fokus auf User-Learning statt AI-Vorschläge |

#### UI-Übersicht:

**In Settings → Mail-Accounts Tabelle:**
```
martina | imap.gmx.net | Aktiv | ✅ AI ✅ Booster | [→ Ändern]
thomas  | mail.beispiel-firma   | Aktiv | ⭕ AI ✅ Booster | [→ Ändern]
```

**Auf der Seite 📬 Absender & Abruf:**
- Card mit detaillierten Erklärungen aller 4 Szenarien
- Pro Account 2 Toggles (checked = aktiviert)
- Live-Speicherung bei Toggle-Änderung
- Toast-Benachrichtigung bei Erfolg

#### So konfigurierst du es:

**Variante 1: Über Settings**
1. Gehe zu **Settings**
2. Finde deinen Account in der **Mail-Accounts** Tabelle
3. Klicke auf **"→ Ändern"** in der Spalte "Abruf-Einstellungen"
4. → Wirst zu **Absender & Abruf** weitergeleitet

**Variante 2: Direkt**
1. Gehe zu **📬 Absender & Abruf** im Menü
2. Finde deine Account-Karte
3. Toggle **"AI-Analyse beim Abruf"** und **"UrgencyBooster (spaCy)"**
4. Änderungen werden automatisch gespeichert

#### Trusted Senders (Whitelist)

**Zusätzlich zur AI-Kontrolle** kannst du vertrauenswürdige Absender definieren, deren Emails automatisch als **"Hoch dringend"** markiert werden.

**Features:**
- ✅ **Account-basiert**: Whitelist pro Mail-Account ODER global für alle
- ✅ **3 Pattern-Typen**: Exakt, Domain (@example.com), Domain+Subdomains
- ✅ **Vorschläge**: System schlägt häufige Absender vor
- ✅ **UrgencyBooster**: Automatische Urgency-Override für gewhitelistete Sender
- ✅ **Dedizierte Seite**: `/whitelist` mit 2-Spalten-Layout
- ✅ **Batch-Operationen**: Mehrere Einträge auf einmal löschen
- ✅ **Live-Filter**: Suche nach Pattern-Namen

**So funktioniert's:**

1. **Gehe zu 🛡️ Whitelist** (in der Navigation) ODER zu Settings → Phase X

2. **Wähle Account-Kontext:**
   - 🌍 **Global (alle Accounts)**: Whitelist gilt für ALLE deine Mail-Accounts
   - 📧 **Spezifischer Account**: Whitelist nur für diesen Account (z.B. nur Geschäft)

3. **Absender manuell hinzufügen:**
   - **Absender-Muster**: `chef@firma.ch` oder `@firma.ch` oder `firma.ch`
   - **Typ**: 
     - 🔒 **Exakt**: Nur exakte Email-Adresse
     - 👥 **Domain**: Alle Emails von `@firma.ch`
     - 🏢 **Domain+Subs**: Auch `test.firma.ch`, `mail.firma.ch` etc.
   - **Für welches Account**: Global oder spezifisch
   - **Label** (optional): `CEO`, `Wichtiger Kunde`, etc.
   - **⚡ UrgencyBooster aktivieren**: Checkbox (empfohlen!)
   - Klicke **"Hinzufügen"**

4. **Vorschläge nutzen:**
   - Klicke **"🔍 Vorschläge laden"**
   - System zeigt häufigste Absender aus gewähltem Account
   - Klicke **"✅ Hinzufügen"** bei einem Vorschlag
   - → Formular wird vorausgefüllt, nur noch bestätigen

**Beispiel-Workflows:**

**Szenario 1: Chef nur auf Geschäfts-Account wichtig**
```
1. Wähle Account: 📧 max.mustermann@firma.ch
2. Pattern: chef@firma.ch
3. Typ: 🔒 Exakt
4. Account: 📧 max.mustermann@firma.ch (spezifisch!)
5. ⚡ aktivieren → Hinzufügen

→ Emails vom Chef im Geschäfts-Account = automatisch "Hoch dringend"  
→ Emails vom Chef im Privat-Account = normale KI-Bewertung
```

**Szenario 2: Firmen-Domain global wichtig**
```
1. Wähle Account: 🌍 Global (alle Accounts)
2. Pattern: @firma.ch
3. Typ: 👥 Domain
4. Account: 🌍 Global
5. ⚡ aktivieren → Hinzufügen

→ ALLE Emails von @firma.ch in ALLEN Accounts = "Hoch dringend"
```

**Account-Badges verstehen:**
- Liste zeigt alle Sender mit Badges:
  - `🌍 Global`: Gilt für alle Accounts
  - `📧 Account 1`: Gilt nur für Account 1
- Beim Wechsel des Account-Selectors werden angezeigt:
  - Account-spezifische Sender des gewählten Accounts
  - + Alle globalen Sender

**Prioritätslogik:**
1. Account-spezifische Whitelist wird zuerst geprüft
2. Falls nicht gefunden → Globale Whitelist
3. Falls dort auch nicht → Normale KI-Bewertung

**Limits:**
- Max. 500 Sender pro Account
- Unbegrenzt global

---

### 11.5 Passwort ändern

> **📸 Screenshot:** Passwort ändern Formular (change_password.html)  
> *Zeige: Altes Passwort, Neues Passwort (2x), Anforderungen-Liste*

![Passwort ändern](images/screenshots/change-password.png)

1. Gehe zu **Einstellungen → Sicherheit**
2. Klicke auf **"Passwort ändern"**
3. Gib dein aktuelles Passwort ein
4. Gib das neue Passwort zweimal ein
5. Klicke auf **"Passwort ändern"**

> ⚠️ Nach der Passwort-Änderung wirst du automatisch ausgeloggt. Deine verschlüsselten Daten bleiben erhalten – nur der Verschlüsselungsschlüssel wird neu verpackt.

### 11.6 2FA & Recovery-Codes

> **📸 Screenshot:** 2FA-Sektion in Einstellungen  
> *Zeige: 2FA-Status, "Recovery-Codes regenerieren" Button*

![2FA-Verwaltung](images/screenshots/2fa-settings.png)

**Recovery-Codes regenerieren:****
1. Klicke auf **"Recovery-Codes neu generieren"**
2. Bestätige mit deinem 2FA-Code
3. **Speichere die neuen Codes!** Die alten sind ab sofort ungültig.

---

## 12. Sicherheit & Datenschutz

### Zero-Knowledge-Architektur

Die App verwendet eine Zero-Knowledge-Architektur. Das bedeutet:

```
┌─────────────────────────────────────────────────────────────┐
│  DEIN BROWSER                                               │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Master-Passwort → KEK (Key Encryption Key)            │ │
│  │ KEK entschlüsselt → DEK (Data Encryption Key)         │ │
│  │ DEK entschlüsselt → Deine Emails (Klartext)           │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ↑
                    Nur hier existiert Klartext!
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  SERVER-DATENBANK                                           │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ encrypted_dek = AES-256-GCM(DEK, KEK)                 │ │
│  │ encrypted_subject = AES-256-GCM(Betreff, DEK)         │ │
│  │ encrypted_body = AES-256-GCM(Inhalt, DEK)             │ │
│  │ encrypted_sender = AES-256-GCM(Absender, DEK)         │ │
│  └───────────────────────────────────────────────────────┘ │
│  → Server sieht NUR verschlüsselte Daten!                  │
└─────────────────────────────────────────────────────────────┘
```

**Was das für dich bedeutet:**
- ✅ Selbst wenn jemand die Datenbank stiehlt, sind deine Emails unlesbar
- ✅ Der Server-Admin kann deine Emails nicht lesen
- ⚠️ Vergisst du dein Passwort, sind deine Daten verloren (kein Recovery möglich!)

### Verwendete Kryptographie

| Komponente | Algorithmus | Parameter |
|------------|-------------|-----------|
| **Passwort-Hashing** | PBKDF2-HMAC-SHA256 | 600.000 Iterationen |
| **Datenverschlüsselung** | AES-256-GCM | 256-bit Key, 96-bit IV |
| **2FA** | TOTP | SHA-1, 30s Intervall, 6 Ziffern |

---

## 13. Fehlerbehebung

### "Emails werden nicht abgerufen"

1. **Prüfe den Account-Status:** Einstellungen → Account → "Aktiviert"?
2. **Teste die Verbindung:** IMAP-Diagnostics → Verbindungstest
3. **Prüfe Zugangsdaten:** Bei vielen Providern brauchst du ein App-Passwort

### "KI-Analyse schlägt fehl"

1. **Prüfe Ollama:** Läuft der Ollama-Dienst? (`systemctl status ollama`)
2. **Prüfe das Modell:** Ist das konfigurierte Modell installiert? (`ollama list`)
3. **Prüfe die Logs:** `tail -f logs/app.log`

### "2FA-Code wird nicht akzeptiert"

1. **Zeit synchronisieren:** TOTP ist zeitbasiert. Prüfe die Uhrzeit deines Handys.
2. **Recovery-Code verwenden:** Falls nichts hilft, nutze einen Recovery-Code.

### "Passwort vergessen"

> ⚠️ **Leider nicht wiederherstellbar.** Zero-Knowledge bedeutet: Ohne dein Passwort kann niemand (auch nicht der Server) deine Daten entschlüsseln. Du musst einen neuen Account erstellen.

### "SQLITE_BUSY Fehler"

Die App verwendet WAL-Mode für parallele Zugriffe. Falls dennoch Probleme auftreten:

```bash
# Prüfe WAL-Status
python3 scripts/verify_wal_mode.py

# Im Notfall: App stoppen, dann
sqlite3 emails.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

---

## Anhang: Screenshot-Checkliste (27 Stück)

| # | Kapitel | Was zeigen | Template/Route |
|---|---------|------------|----------------|
| 1 | 2.1 | Registrierungs-Formular | `register.html` |
| 2 | 2.2 | 2FA-Setup mit QR-Code | `setup_2fa.html` |
| 3 | 2.2 | Recovery-Codes Liste | `recovery_codes.html` |
| 4 | 2.3 | Einstellungen > "Neuen Account hinzufügen" | `settings.html` |
| 5 | 2.3 | Mail-Account Formular (IMAP) | Modal in settings |
| 6 | 3 | Dashboard mit gefüllter 3×3 Matrix | `dashboard.html` |
| 7 | 4 | Email-Liste mit Filter-Leiste | `list_view.html` |
| 8 | 4.1 | Filter-Dropdowns aufgeklappt | list_view.html |
| 9 | 4.3 | Suchfeld mit Semantik-Toggle | list_view.html |
| 10 | 5 | Email-Detail komplett | `email_detail.html` |
| 11 | 5.1 | KI-Analyse Box | email_detail.html |
| 12 | 5.2 | Tag-Bereich mit Badges | email_detail.html |
| 13 | 5.3 | "Bewertung korrigieren" Modal | base.html Modal |
| 14 | 5.4 | Buttons "Optimieren" / "Neu verarbeiten" | email_detail.html |
| 15 | 5.5 | IMAP-Action Buttons | email_detail.html |
| 16 | 5.6 | Reply-Draft Modal mit Ton-Auswahl | email_detail.html |
| 17 | 5.7 | "Ähnliche Emails" Card | email_detail.html |
| 18 | 6 | Tag-Verwaltung Seite | `tags.html` |
| 19 | 6.1 | "Neuer Tag" Modal mit Farbauswahl | tags.html Modal |
| 20 | 7 | Auto-Rules Seite | `rules_management.html` |
| 21 | 7.2 | "Neue Regel" Modal | rules_management.html |
| 22 | 7.5 | Template-Dropdown | rules_management.html |
| 23 | 7.6 | Dry-Run Ergebnis | rules_management.html |
| 24 | 8 | IMAP-Diagnostics Dashboard | `imap_diagnostics.html` |
| 25 | 8 | Sync-Check Ergebnis | imap_diagnostics.html |
| 26 | 9 | Einstellungen komplett | `settings.html` |
| 27 | 9.2 | SMTP-Einstellungen im Account-Formular | settings.html |

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
| **Auto-Rules** | Automatische Regeln, die Aktionen bei Email-Eingang ausführen |
| **Base Model** | KI-Modell für schnelle Erst-Analyse (z.B. llama3.2:1b) |
| **DEK** | Data Encryption Key – verschlüsselt deine Emails |
| **Embedding** | Semantischer Fingerabdruck eines Textes (Vektor aus Zahlen) |
| **Embedding Model** | KI-Modell für semantische Vektoren (z.B. all-minilm:22m) |
| **IMAP** | Protokoll zum Abrufen von Emails |
| **KEK** | Key Encryption Key – verschlüsselt den DEK (aus Passwort abgeleitet) |
| **OAuth** | Anmeldeverfahren ohne Passwort-Weitergabe (z.B. "Mit Google anmelden") |
| **Ollama** | Lokaler KI-Server zum Ausführen von LLMs |
| **Optimize Model** | KI-Modell für tiefe Analyse (z.B. llama3.2:3b, claude-haiku) |
| **Semantische Suche** | Suche nach Bedeutung statt exakten Wörtern |
| **Similarity Score** | Ähnlichkeitswert zwischen zwei Texten (0-100%) |
| **SMTP** | Protokoll zum Versenden von Emails |
| **Thread** | Email-Konversation (mehrere Emails zum gleichen Thema) |
| **Thread-Context** | Vorherige Emails einer Konversation als Kontext für KI |
| **TOTP** | Time-based One-Time Password – die 6-stelligen 2FA-Codes |
| **UIDVALIDITY** | IMAP-Kennung, ob ein Ordner neu aufgebaut wurde |
| **Zero-Knowledge** | Server-Architektur, bei der der Server keine Klartext-Daten sieht |

---

*Dieses Handbuch wurde für KI-Mail-Helper erstellt. Bei Fragen oder Problemen: GitHub Issues.*
