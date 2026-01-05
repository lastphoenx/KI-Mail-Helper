# 📧 KI-Mail-Helper – Benutzerhandbuch

**Version:** 1.0  
**Stand:** 4. Januar 2026

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
   - 5.7 Ähnliche Emails finden
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
8. [IMAP-Diagnostics](#8-imap-diagnostics)
9. [Einstellungen](#9-einstellungen)
   - 9.1 Mail-Accounts verwalten
   - 9.2 SMTP konfigurieren (Email-Versand)
   - 9.3 KI-Provider konfigurieren
   - 9.4 Passwort ändern
   - 9.5 2FA & Recovery-Codes
10. [Sicherheit & Datenschutz](#10-sicherheit--datenschutz)
11. [Fehlerbehebung](#11-fehlerbehebung)

---

## 1. Einführung

KI-Mail-Helper ist ein selbst-gehosteter Email-Organizer, der künstliche Intelligenz nutzt, um deine Emails automatisch zu analysieren, zu priorisieren und zu beantworten.

**Kernfunktionen:**

| Feature | Beschreibung |
|---------|--------------|
| **🎯 3×3 Prioritäts-Matrix** | Automatische Bewertung nach Dringlichkeit × Wichtigkeit |
| **🔍 Semantische Suche** | Finde Emails nach Bedeutung, nicht nur Keywords |
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

### 5.7 Ähnliche Emails finden

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
> *Zeige: Vorgeschlagene Tags als klickbare Badges*

![Tag-Vorschläge](images/screenshots/tag-suggestions.png)

Die KI schlägt automatisch Tags vor, basierend auf:

**Zwei Arten von Tag-Embeddings:**

| Art | Quelle | Qualität |
|-----|--------|----------|
| **Gelernt** | Manuell zugewiesene Tags | ⭐⭐⭐⭐⭐ Beste Ergebnisse |
| **Beschreibung** | Tag-Name als Text | ⭐⭐⭐ Gut für neue Tags |

**So funktioniert's:**
1. Jede Email bekommt ein **Embedding** (semantischer Fingerabdruck)
2. Jeder Tag hat ebenfalls ein Embedding
3. Die KI vergleicht: "Wie ähnlich ist diese Email zu Emails mit Tag X?"
4. Tags mit hoher Ähnlichkeit (>70%) werden vorgeschlagen

**Lernen aus deinem Verhalten:**
- Je mehr Emails du manuell taggst, desto besser werden die Vorschläge
- Das System lernt: "Emails über Rechnungen bekommen meist den Tag 'Finanzen'"
- Nach ~5-10 manuellen Zuweisungen pro Tag werden Vorschläge sehr genau

> 💡 **Tipp:** Starte mit wenigen Tags und tagge konsequent. Die KI lernt schnell!

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

## 8. IMAP-Diagnostics

> **📸 Screenshot:** IMAP-Diagnostics Dashboard (/imap-diagnostics)  
> *Zeige: Account-Auswahl, Test-Buttons, Ergebnis-Bereich*

![IMAP-Diagnostics](images/screenshots/imap-diagnostics.png)

Unter **🔧 IMAP-Test** findest du Diagnose-Tools für deine Mail-Accounts.

### 8.1 Verfügbare Tests

| Test | Beschreibung |
|------|--------------|
| **🔌 Verbindungstest** | Prüft IMAP-Server-Erreichbarkeit und Login |
| **📁 Ordner-Liste** | Zeigt alle IMAP-Ordner mit Email-Anzahl |
| **🔄 DB-Sync-Check** | Vergleicht lokale DB mit IMAP-Server |
| **📊 Mail-Count** | Zählt Emails pro Ordner (Remote vs. Lokal) |

### 8.2 DB-Sync-Check verstehen

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

### 8.3 Multi-Folder Ansicht

> **📸 Screenshot:** Multi-Folder Übersicht mit aufgeklapptem Detail  
> *Zeige: Ordner-Tree mit Details zu UIDs und Flags*

![Multi-Folder Ansicht](images/screenshots/multi-folder-view.png)

Klicke auf einen Ordner, um Details zu sehen:
- Einzelne Email-UIDs
- IMAP-Flags vs. DB-Status
- Mismatch-Highlighting

> 💡 **Tipp:** Bei großen Deltas nutze "Jetzt abrufen" in den Einstellungen, um fehlende Emails zu synchronisieren.

---

## 9. Einstellungen

> **📸 Screenshot:** Einstellungen-Seite komplett (settings.html)  
> *Zeige: Alle Sektionen (Mail-Accounts, KI, SMTP, Sicherheit)*

![Einstellungen](images/screenshots/settings.png)

### 9.1 Mail-Accounts verwalten

> **📸 Screenshot:** Mail-Account Liste in Einstellungen  
> *Zeige: Account-Karten mit Status, Bearbeiten/Löschen Buttons*

![Mail-Account Liste](images/screenshots/settings-accounts.png)

**Account bearbeiten:**
1. Klicke auf **"Bearbeiten"** beim gewünschten Account
2. Ändere Server, Port oder Zugangsdaten
3. Klicke auf **"Speichern"**

**Account löschen:**
1. Klicke auf **"Löschen"**
2. Bestätige im Dialog

> ⚠️ Beim Löschen werden alle Emails dieses Accounts aus der lokalen Datenbank entfernt!

**Emails abrufen:**
- **Manuell:** Klicke auf **"Jetzt abrufen"** beim Account
- **Automatisch:** Ein Hintergrund-Job prüft regelmäßig (alle 15 Min.)

> **📸 Screenshot:** Email-Abruf Progress-Modal  
> *Zeige: Fortschrittsbalken, "X von Y Emails verarbeitet"*

![Email-Abruf Progress](images/screenshots/fetch-progress.png)

### 9.2 SMTP konfigurieren (Email-Versand)

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

### 9.3 KI-Provider konfigurieren

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

### 9.4 Passwort ändern

> **📸 Screenshot:** Passwort ändern Formular (change_password.html)  
> *Zeige: Altes Passwort, Neues Passwort (2x), Anforderungen-Liste*

![Passwort ändern](images/screenshots/change-password.png)

1. Gehe zu **Einstellungen → Sicherheit**
2. Klicke auf **"Passwort ändern"**
3. Gib dein aktuelles Passwort ein
4. Gib das neue Passwort zweimal ein
5. Klicke auf **"Passwort ändern"**

> ⚠️ Nach der Passwort-Änderung wirst du automatisch ausgeloggt. Deine verschlüsselten Daten bleiben erhalten – nur der Verschlüsselungsschlüssel wird neu verpackt.

### 9.5 2FA & Recovery-Codes

> **📸 Screenshot:** 2FA-Sektion in Einstellungen  
> *Zeige: 2FA-Status, "Recovery-Codes regenerieren" Button*

![2FA-Verwaltung](images/screenshots/2fa-settings.png)

**Recovery-Codes regenerieren:****
1. Klicke auf **"Recovery-Codes neu generieren"**
2. Bestätige mit deinem 2FA-Code
3. **Speichere die neuen Codes!** Die alten sind ab sofort ungültig.

---

## 10. Sicherheit & Datenschutz

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

## 11. Fehlerbehebung

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
