# IMAPClient - Komplettes Handbuch für Email-Klassifizierung

**Version:** IMAPClient 3.0.0+  
**Zielgruppe:** Email-Klassifizierungs-System mit KI-Integration  
**Python:** 3.8+

---

## 📚 Inhaltsverzeichnis

1. [Verbindung & Authentifizierung](#verbindung--authentifizierung)
2. [Ordner-Management](#ordner-management)
3. [Email-Suche & Filterung](#email-suche--filterung)
4. [Emails Abrufen (FETCH) - Das Herzstück](#emails-abrufen-fetch---das-herzstück)
5. [Flags & Labels Management](#flags--labels-management)
6. [Emails Verschieben & Organisieren](#emails-verschieben--organisieren)
7. [IDLE - Echtzeit-Monitoring](#idle---echtzeit-monitoring)
8. [Gmail-Spezifische Features](#gmail-spezifische-features)
9. [Error Handling & Exceptions](#error-handling--exceptions)
10. [Performance & Best Practices](#performance--best-practices)
11. [Komplette Workflow-Beispiele](#komplette-workflow-beispiele)

---

## 1. Verbindung & Authentifizierung

### IMAPClient Konstruktor

```python
class IMAPClient(host: str, 
                 port: int = None, 
                 use_uid: bool = True, 
                 ssl: bool = True, 
                 stream: bool = False, 
                 ssl_context: SSLContext | None = None, 
                 timeout: float | None = None)
```

**Parameter:**
- `host`: IMAP Server-Adresse (z.B. 'imap.gmail.com')
- `port`: Standard: 993 (SSL) oder 143 (unverschlüsselt)
- `use_uid`: `True` = Message UIDs nutzen (empfohlen!), `False` = Sequence Numbers
- `ssl`: `True` = Verschlüsselte Verbindung (empfohlen!)
- `ssl_context`: Eigener SSL-Context für erweiterte TLS-Kontrolle
- `timeout`: Float (Sekunden) oder `SocketTimeout(connect=15, read=60)`

**SocketTimeout für getrennte Timeouts:**
```python
from imapclient import IMAPClient, SocketTimeout

# Unterschiedliche Timeouts für Connect und Read/Write
timeout = SocketTimeout(connect=15, read=60)
client = IMAPClient('imap.gmail.com', timeout=timeout)
```

**Context Manager (empfohlen):**
```python
with IMAPClient(host="imap.gmail.com") as client:
    client.login("user@gmail.com", "password")
    # Automatisches logout() und Verbindungsabbau
```

### Authentifizierungs-Methoden

#### Standard Login
```python
login(username: str, password: str)
```

```python
client = IMAPClient('imap.gmail.com')
response = client.login('user@gmail.com', 'password')
# Rückgabe: Server-Response String
```

#### OAuth2 (Gmail, Yahoo)
```python
oauth2_login(user: str, access_token: str, mech: str = 'XOAUTH2', vendor: str | None = None)
```

```python
# Gmail
client.oauth2_login('user@gmail.com', 'ya29.access_token', mech='XOAUTH2')

# Yahoo (benötigt vendor)
client.oauth2_login('user@yahoo.com', 'token', mech='XOAUTH2', vendor='yahoo')
```

#### OAuth Bearer (moderner Standard)
```python
oauthbearer_login(identity: str, access_token: str)
```

```python
client.oauthbearer_login('user@gmail.com', 'access_token')
```

#### PLAIN Authentifizierung
```python
plain_login(identity: str, password: str, authorization_identity: str = None)
```

#### SASL Mechanismen (erweitert)
```python
sasl_login(mech_name: str, mech_callable: Callable)
```

**Beispiel für PLAIN via SASL:**
```python
plain_mech = lambda _: f"\0{username}\0{password}".encode('utf-8')
client.sasl_login("PLAIN", plain_mech)
```

**Beispiel für komplexe SASL-Mechanismen:**
```python
def custom_mech(challenge):
    if challenge == b"Username:":
        return username.encode("utf-8")
    elif challenge == b"Password:":
        return password.encode("utf-8")
    return b""

client.sasl_login("CUSTOM", custom_mech)
```

### Verbindung beenden

```python
# Empfohlene Methode: Logout + Verbindung schließen
client.logout()

# Nur Verbindung schließen (OHNE Logout)
client.shutdown()

# Context Manager macht das automatisch
with IMAPClient('imap.gmail.com') as client:
    pass  # logout() wird automatisch aufgerufen
```

### Server-Informationen

```python
# Server-Begrüßungsnachricht
welcome_msg = client.welcome

# Server-Capabilities prüfen
caps = client.capabilities()
# Rückgabe: Set wie {b'IMAP4REV1', b'IDLE', b'NAMESPACE', ...}

# Bestimmte Capability prüfen
if client.has_capability('IDLE'):
    print("Server unterstützt IDLE")

# Server-Implementierungsdetails (ID extension)
server_info = client.id_({'name': 'MyEmailClassifier', 'version': '1.0'})
# Rückgabe: Dict wie {'name': 'Dovecot', 'version': '2.3.16'}

# NOOP - Status-Updates abrufen + Auto-Logout-Timer zurücksetzen
response, updates = client.noop()
# Beispiel: (b'NOOP completed.', [(4, b'EXISTS'), (3, b'FETCH', ...)])
```

---

## 2. Ordner-Management

### Ordner auflisten

#### list_folders() - Alle Ordner
```python
list_folders(directory='', pattern='*')
```

**Rückgabe:** Liste von `(flags, delimiter, name)` Tupeln

```python
# Alle Ordner rekursiv
folders = client.list_folders()
# Beispiel: [(b'\\HasNoChildren', '/', 'INBOX'), 
#            (b'\\HasChildren', '/', 'Work'), 
#            (b'\\HasNoChildren', '/', 'Work/Projects')]

# Nur Unterordner von "Work"
work_folders = client.list_folders(directory='Work')

# Mit Wildcards
# * = 0 oder mehr beliebige Zeichen
# % = 0 oder mehr Zeichen AUSSER Delimiter
inbox_subfolders = client.list_folders(directory='INBOX', pattern='%')

# Ordner durchiterieren
for flags, delimiter, folder_name in client.list_folders():
    print(f"Ordner: {folder_name}")
    print(f"  Flags: {flags}")
    print(f"  Delimiter: '{delimiter}'")
```

**Wichtige Folder-Flags:**
- `\HasChildren` / `\HasNoChildren` - Unterordner vorhanden/nicht vorhanden
- `\Noselect` - Ordner kann nicht ausgewählt werden (nur Container)
- `\Marked` / `\Unmarked` - Ordner hat neue Nachrichten seit letzter Prüfung
- `\Drafts`, `\Sent`, `\Trash`, `\Junk`, `\Archive` - Spezielle Ordner

#### list_sub_folders() - Abonnierte Ordner
```python
list_sub_folders(directory='', pattern='*')
```

```python
# Nur abonnierte Ordner
subscribed = client.list_sub_folders()
```

#### namespace() - Namespace-Informationen
```python
namespace()
```

**Rückgabe:** `(personal, other, shared)` Tuple

```python
namespaces = client.namespace()

# Zugriff per Index oder Attribut
personal_ns = namespaces.personal  # oder namespaces[0]
other_ns = namespaces.other        # oder namespaces[1]
shared_ns = namespaces.shared      # oder namespaces[2]

# Beispiel:
# personal: [('', '/')]
# other: [('~', '/')]
# shared: [('#shared/', '/'), ('#public/', '/')]
```

#### xlist_folders() - Gmail-spezifisch (deprecated)
```python
xlist_folders(directory='', pattern='*')
```

**Hinweis:** XLIST ist deprecated, nutze stattdessen `list_folders()` mit Special-Use-Attributen.

```python
# Liefert Ordner mit lokalisierten Namen und speziellen Flags
# Beispiel bei Gmail:
# [((b'\\HasNoChildren', b'\\Inbox'), b'/', u'Inbox'),
#  ((b'\\HasNoChildren', b'\\Sent'), b'/', u'[Gmail]/Sent Mail'),
#  ((b'\\HasNoChildren', b'\\Trash'), b'/', u'[Gmail]/Trash')]
```

### Spezielle Ordner finden

```python
find_special_folder(folder_flag)
```

**Verfügbare Flags:**
- `imapclient.SENT` - Gesendete Nachrichten
- `imapclient.DRAFTS` - Entwürfe
- `imapclient.TRASH` - Papierkorb
- `imapclient.JUNK` - Spam/Junk
- `imapclient.ARCHIVE` - Archiv

```python
import imapclient

# Automatisch richtigen Sent-Ordner finden
sent_folder = client.find_special_folder(imapclient.SENT)
# Rückgabe: 'INBOX.Sent' oder '[Gmail]/Sent Mail' oder None

if sent_folder:
    client.select_folder(sent_folder)
```

### Ordner auswählen

```python
select_folder(folder: str, readonly: bool = False)
```

**Rückgabe:** Dictionary mit Ordner-Informationen

```python
info = client.select_folder('INBOX')

# Garantierte Keys:
# b'EXISTS' - Anzahl Nachrichten im Ordner
# b'FLAGS' - Verfügbare Flags
# b'RECENT' - Anzahl kürzlich eingetroffener Nachrichten
# b'PERMANENTFLAGS' - Flags die dauerhaft gesetzt werden können
# b'READ-WRITE' - Ordner ist schreibbar
# b'UIDNEXT' - Nächste zu vergebende UID
# b'UIDVALIDITY' - UID-Gültigkeit (ändert sich bei Ordner-Reset)

print(f"Ordner hat {info[b'EXISTS']} Nachrichten")
print(f"Davon {info[b'RECENT']} neu")
print(f"Verfügbare Flags: {info[b'FLAGS']}")

# Read-only Modus (keine Änderungen möglich)
info = client.select_folder('INBOX', readonly=True)
```

### Ordner-Status ohne Auswählen

```python
folder_status(folder: str, what: list = None)
```

**Standard-What:** `('MESSAGES', 'RECENT', 'UIDNEXT', 'UIDVALIDITY', 'UNSEEN')`

**Verfügbare Status-Items:**
- `MESSAGES` - Gesamtanzahl Nachrichten
- `RECENT` - Kürzlich eingetroffen
- `UNSEEN` - Ungelesen
- `UIDNEXT` - Nächste UID
- `UIDVALIDITY` - UID-Gültigkeit
- `HIGHESTMODSEQ` - Höchste Modifikations-Sequenznummer (bei CONDSTORE)

```python
# Status abfragen ohne Ordner zu wechseln
status = client.folder_status('INBOX', ['MESSAGES', 'UNSEEN'])
# Rückgabe: {b'MESSAGES': 1234, b'UNSEEN': 42}

total = status[b'MESSAGES']
unread = status[b'UNSEEN']

# Für mehrere Ordner
folder_stats = {}
for flags, delimiter, folder_name in client.list_folders():
    try:
        status = client.folder_status(folder_name, ['MESSAGES', 'UNSEEN'])
        folder_stats[folder_name] = {
            'total': status[b'MESSAGES'],
            'unread': status[b'UNSEEN']
        }
    except Exception as e:
        print(f"Fehler bei {folder_name}: {e}")
```

### Ordner-Operationen

```python
# Ordner existiert?
exists = client.folder_exists('Work/Projects')

# Ordner erstellen
response = client.create_folder('Work/NewProject')

# Ordner umbenennen
response = client.rename_folder('Work/OldName', 'Work/NewName')

# Ordner löschen
response = client.delete_folder('Work/TempFolder')

# Ordner schließen (aktuelle Selektion)
response = client.close_folder()

# Ordner abwählen (ohne Expunge)
response = client.unselect_folder()

# Ordner abonnieren/deabonnieren
response = client.subscribe_folder('Work/Important')
response = client.unsubscribe_folder('Work/Archive')
```

---

## 3. Email-Suche & Filterung

### search() - Die Hauptsuchmethode

```python
search(criteria='ALL', charset=None)
```

**Rückgabe:** Liste von Message-UIDs (oder Sequence Numbers wenn `use_uid=False`)

#### Einfache Such-Kriterien (Liste empfohlen)

```python
# ALLE Nachrichten
all_msgs = client.search(['ALL'])

# Ungelesene Nachrichten
unseen = client.search(['UNSEEN'])

# Markierte Nachrichten
flagged = client.search(['FLAGGED'])

# Gelöschte Nachrichten
deleted = client.search(['DELETED'])

# Beantwortete Nachrichten
answered = client.search(['ANSWERED'])

# Entwürfe
drafts = client.search(['DRAFT'])
```

#### Datums-basierte Suche

```python
from datetime import date, timedelta

# Nachrichten seit einem bestimmten Datum
since_date = date(2024, 1, 1)
recent = client.search(['SINCE', since_date])

# Vor einem Datum
before_date = date(2023, 12, 31)
old = client.search(['BEFORE', before_date])

# An einem bestimmten Datum
on_date = date(2024, 1, 15)
on_that_day = client.search(['ON', on_date])

# Letzte 7 Tage
week_ago = date.today() - timedelta(days=7)
last_week = client.search(['SINCE', week_ago])

# Zwischen zwei Daten
start = date(2024, 1, 1)
end = date(2024, 1, 31)
january = client.search(['SINCE', start, 'BEFORE', end])
```

#### Absender & Empfänger

```python
# Von einem bestimmten Absender
from_mike = client.search(['FROM', 'mike@example.com'])

# An einen bestimmten Empfänger
to_alice = client.search(['TO', 'alice@example.com'])

# CC
cc_bob = client.search(['CC', 'bob@example.com'])

# BCC
bcc_charlie = client.search(['BCC', 'charlie@example.com'])
```

#### Betreff & Inhalt

```python
# Betreff enthält
subject_invoice = client.search(['SUBJECT', 'Rechnung'])

# Body enthält
body_urgent = client.search(['BODY', 'dringend'])

# Text (Body ODER Betreff) enthält
text_meeting = client.search(['TEXT', 'Meeting'])

# Hinweis: TEXT durchsucht sowohl Subject als auch Body
```

#### Größe

```python
# Größer als 1MB
large = client.search(['LARGER', 1000000])

# Kleiner als 10KB
small = client.search(['SMALLER', 10000])
```

#### Kombinierte Suche (UND-Verknüpfung)

```python
# Ungelesen UND von Mike
criteria = ['UNSEEN', 'FROM', 'mike@example.com']
results = client.search(criteria)

# Ungelesen UND seit letzter Woche UND mit "Wichtig" im Betreff
week_ago = date.today() - timedelta(days=7)
criteria = ['UNSEEN', 'SINCE', week_ago, 'SUBJECT', 'Wichtig']
results = client.search(criteria)
```

#### NICHT (NOT) Operator

```python
# NICHT gelöscht
not_deleted = client.search(['NOT', 'DELETED'])

# NICHT von Mike
not_from_mike = client.search(['NOT', 'FROM', 'mike@example.com'])

# Komplexer: NICHT (gelöscht ODER Entwurf)
# Hier müssen wir verschachteln
not_deleted_or_draft = client.search(['NOT', ['DELETED'], 'NOT', ['DRAFT']])
```

#### ODER (OR) Operator

```python
# Von Mike ODER von Alice
or_senders = client.search(['OR', 'FROM', 'mike@example.com', 'FROM', 'alice@example.com'])

# Wichtig ODER ungelesen
or_criteria = client.search(['OR', 'FLAGGED', 'UNSEEN'])
```

#### Verschachtelte Suche (komplexe Logik)

```python
# NICHT (mit "foo" im Betreff UND markiert)
# = Nachrichten die ENTWEDER nicht "foo" im Betreff haben ODER nicht markiert sind
complex = client.search(['NOT', ['SUBJECT', 'foo', 'FLAGGED']])

# (Von Mike ODER von Alice) UND ungelesen
nested = client.search([
    'UNSEEN',
    'OR', 'FROM', 'mike@example.com', 'FROM', 'alice@example.com'
])
```

#### Charset-Unterstützung

```python
# Standardmäßig US-ASCII
# UTF-8 für Unicode-Suche
results = client.search(['SUBJECT', 'Müller'], charset='UTF-8')

# Unicode-Strings werden automatisch nach UTF-8 encodiert
results = client.search(['FROM', 'müller@example.com'], charset='UTF-8')
```

#### UID-basierte Suche

```python
# Bestimmte UIDs
specific = client.search(['UID', '1000:1005'])

# UIDs größer als X
newer_than = client.search(['UID', '1000:*'])
```

#### MODSEQ (mit CONDSTORE Extension)

```python
# Server-Capability prüfen
if client.has_capability('CONDSTORE'):
    # Seit letzter Änderung
    changed = client.search(['MODSEQ', 123456])
    
    # Das Ergebnis hat ein .modseq Attribut
    if hasattr(changed, 'modseq'):
        print(f"Höchste MODSEQ: {changed.modseq}")
```

#### Alternative: String-basierte Suche (NICHT empfohlen)

```python
# Einzelner String (weniger sicher, keine automatische Quotierung)
results = client.search('UNSEEN')
results = client.search('TEXT "foo bar" FLAGGED')
results = client.search('SINCE 03-Apr-2024')

# Besser: Nutze Listen-Format (automatische Quotierung)
```

### sort() - Sortierte Suche

```python
sort(sort_criteria, criteria='ALL', charset='UTF-8')
```

**Verfügbare Sort-Kriterien:**
- `ARRIVAL` - Nach Ankunftszeit
- `CC` - Nach CC-Header
- `DATE` - Nach Date-Header
- `FROM` - Nach From-Header
- `REVERSE <kriterium>` - Umgekehrte Sortierung
- `SIZE` - Nach Größe
- `SUBJECT` - Nach Betreff
- `TO` - Nach To-Header

```python
# Nach Ankunftszeit sortiert
by_arrival = client.sort(['ARRIVAL'])

# Nach Betreff, dann Ankunftszeit
by_subject = client.sort(['SUBJECT', 'ARRIVAL'])

# Neueste zuerst (REVERSE)
newest_first = client.sort(['REVERSE', 'ARRIVAL'])

# Größte zuerst
largest_first = client.sort(['REVERSE', 'SIZE'])

# Mit Suchfilter kombinieren
unseen_sorted = client.sort(['ARRIVAL'], criteria=['UNSEEN'])
```

**Wichtig:** SORT ist eine Extension - prüfe vorher mit `has_capability('SORT')`

### thread() - Thread-Gruppierung

```python
thread(algorithm='REFERENCES', criteria='ALL', charset='UTF-8')
```

**Algorithmen:**
- `REFERENCES` - Nach References/In-Reply-To Header
- `ORDEREDSUBJECT` - Nach Betreff

**Rückgabe:** Liste von Thread-Listen (verschachtelte Struktur)

```python
# Threads abrufen
threads = client.thread()
# Beispiel: ((1, 2), (3,), (4, 5, 6))
# = 3 Threads: [1,2], [3], [4,5,6]

# Nur ungelesene Threads
unread_threads = client.thread(criteria=['UNSEEN'])

# Über Threads iterieren
for thread in threads:
    print(f"Thread mit {len(thread)} Nachrichten: {thread}")
```

### gmail_search() - Gmail-spezifische Suche

```python
gmail_search(query: str, charset='UTF-8')
```

**Nutzt Gmail's X-GM-RAW Extension**

```python
# Gmail-Suchsyntax
results = client.gmail_search('has:attachment in:unread')
results = client.gmail_search('from:mike subject:wichtig')
results = client.gmail_search('is:starred -is:read')
results = client.gmail_search('larger:5M older_than:1y')

# Mit Unicode
results = client.gmail_search('from:müller@example.com', charset='UTF-8')
```

**Hinweis:** Funktioniert NUR bei Gmail (prüfe mit `has_capability('X-GM-RAW')`)

---

## 4. Emails Abrufen (FETCH) - Das Herzstück

### fetch() - Die wichtigste Methode für Email-Klassifizierung

```python
fetch(messages, data, modifiers=None)
```

**Parameter:**
- `messages`: Liste von UIDs (oder Sequence Numbers)
- `data`: Liste von Daten-Selektoren
- `modifiers`: Optional, für Extensions (z.B. CONDSTORE)

**Rückgabe:** Dictionary `{UID: {data_items...}, UID: {...}}`

### Wichtige Data-Selektoren

#### Basis-Informationen

```python
# Alle Flags
data = ['FLAGS']

# Interne Datum/Zeit (Server-Empfangszeit)
data = ['INTERNALDATE']

# Nachrichtengröße in Bytes
data = ['RFC822.SIZE']

# UID und Sequence Number
# UID wird als Key verwendet, SEQ ist im Result-Dict
data = ['FLAGS']  # SEQ wird immer automatisch mitgeliefert
```

#### Envelope - Strukturierte Header-Daten

```python
# Envelope (Von, An, Betreff, Datum, etc.)
data = ['ENVELOPE']

result = client.fetch([msg_id], ['ENVELOPE'])
envelope = result[msg_id][b'ENVELOPE']

# Envelope-Struktur:
# envelope.date          - datetime oder None
# envelope.subject       - bytes
# envelope.from_         - Tuple von Address-Objekten oder None
# envelope.sender        - Tuple von Address-Objekten oder None
# envelope.reply_to      - Tuple von Address-Objekten oder None
# envelope.to            - Tuple von Address-Objekten oder None
# envelope.cc            - Tuple von Address-Objekten oder None
# envelope.bcc           - Tuple von Address-Objekten oder None
# envelope.in_reply_to   - bytes (Message-ID)
# envelope.message_id    - bytes (Message-ID)

# Address-Objekte haben:
# address.name           - "Personal Name" (bytes oder None)
# address.route          - SMTP Route (selten genutzt, bytes oder None)
# address.mailbox        - Mailbox-Name (vor dem @, bytes)
# address.host           - Host/Domain (nach dem @, bytes)

# Beispiel: Absender extrahieren
if envelope.from_ and len(envelope.from_) > 0:
    sender = envelope.from_[0]
    email = f"{sender.mailbox.decode()}@{sender.host.decode()}"
    name = sender.name.decode() if sender.name else ""
    print(f"{name} <{email}>")
```

#### Headers - Spezifische Header abrufen

```python
# Bestimmte Header
data = ['BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)]']

# Alle Header
data = ['BODY[HEADER]']

# RFC822.HEADER (Alias für BODY[HEADER])
data = ['RFC822.HEADER']

# Einzelne Header
result = client.fetch([msg_id], ['BODY[HEADER.FIELDS (FROM)]'])
from_header = result[msg_id][b'BODY[HEADER.FIELDS (FROM)]']
```

#### Body - Email-Inhalt

```python
# Komplette Email (Header + Body)
data = ['RFC822']

# Nur Body-Text (ohne Header)
data = ['BODY[TEXT]']

# Peek-Varianten (setzen \Seen Flag NICHT)
data = ['BODY.PEEK[TEXT]']
data = ['RFC822.PEEK']

# Bestimmte MIME-Parts
data = ['BODY[1]']          # Erster Part
data = ['BODY[1.1]']        # Erster Sub-Part des ersten Parts
data = ['BODY[2.HEADER]']   # Header des zweiten Parts
data = ['BODY[2.MIME]']     # MIME-Header des zweiten Parts
```

#### BODYSTRUCTURE - MIME-Struktur

```python
# Body-Struktur (ohne Inhalt, nur Metadaten)
data = ['BODYSTRUCTURE']

# Body-Struktur (vereinfacht)
data = ['BODY']

# Hilfreich für:
# - Attachment-Erkennung
# - MIME-Type-Ermittlung
# - Content-Disposition
# - Multipart-Struktur
```

#### Gmail-spezifische Daten

```python
# Gmail Message-ID (unveränderlich)
data = ['X-GM-MSGID']

# Gmail Thread-ID
data = ['X-GM-THRID']

# Gmail Labels
data = ['X-GM-LABELS']
```

### Praktische FETCH-Beispiele

#### Beispiel 1: Minimale Metadaten für Klassifizierung

```python
# Für AI-Klassifizierung: Flags, Envelope, Größe
msg_ids = client.search(['UNSEEN'])

if msg_ids:
    data = ['FLAGS', 'ENVELOPE', 'RFC822.SIZE', 'INTERNALDATE']
    results = client.fetch(msg_ids, data)
    
    for msg_id, msg_data in results.items():
        flags = msg_data[b'FLAGS']
        envelope = msg_data[b'ENVELOPE']
        size = msg_data[b'RFC822.SIZE']
        date = msg_data[b'INTERNALDATE']
        seq = msg_data[b'SEQ']
        
        # Absender extrahieren
        if envelope.from_:
            sender = envelope.from_[0]
            sender_email = f"{sender.mailbox.decode()}@{sender.host.decode()}"
        
        # Betreff extrahieren
        subject = envelope.subject.decode('utf-8', errors='ignore') if envelope.subject else ""
        
        print(f"UID {msg_id}: {sender_email} - {subject} ({size} bytes)")
```

#### Beispiel 2: Email-Body für AI-Analyse

```python
# Kompletten Inhalt für Text-Analyse
msg_ids = client.search(['UNSEEN'])

if msg_ids:
    # PEEK um \Seen nicht zu setzen
    results = client.fetch(msg_ids, ['BODY.PEEK[]'])
    
    for msg_id, msg_data in results.items():
        raw_email = msg_data[b'BODY[]']
        
        # Mit Python's email-Modul parsen
        import email
        msg = email.message_from_bytes(raw_email)
        
        # Text extrahieren
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    break
        else:
            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        
        # An AI senden
        classification = classify_with_ai(body)
```

#### Beispiel 3: Attachments erkennen

```python
results = client.fetch(msg_ids, ['BODYSTRUCTURE'])

for msg_id, msg_data in results.items():
    bodystructure = msg_data[b'BODYSTRUCTURE']
    
    # BodyStructure analysieren
    def has_attachments(bs):
        # Vereinfachtes Beispiel - in Realität komplexer
        if isinstance(bs, tuple) and len(bs) > 0:
            # Prüfe auf 'attachment' in Content-Disposition
            return True  # Detaillierte Implementierung erforderlich
        return False
    
    if has_attachments(bodystructure):
        print(f"Message {msg_id} hat Attachments")
```

#### Beispiel 4: Batch-Processing mit Modifiers

```python
# Mit CHANGEDSINCE (CONDSTORE Extension)
if client.has_capability('CONDSTORE'):
    # Nur geänderte Nachrichten seit letztem Check
    results = client.fetch(
        msg_ids, 
        ['FLAGS', 'ENVELOPE'],
        modifiers=['CHANGEDSINCE 123456']
    )
```

#### Beispiel 5: Effizientes Abrufen vieler Emails

```python
# In Batches von 100 verarbeiten
msg_ids = client.search(['ALL'])

BATCH_SIZE = 100
for i in range(0, len(msg_ids), BATCH_SIZE):
    batch = msg_ids[i:i+BATCH_SIZE]
    
    results = client.fetch(batch, ['FLAGS', 'ENVELOPE', 'RFC822.SIZE'])
    
    for msg_id, msg_data in results.items():
        # Verarbeite Batch
        process_message(msg_data)
```

### FETCH Rückgabe-Format

```python
# Beispiel-Rückgabe:
{
    3230: {
        b'FLAGS': (b'\\Seen',),
        b'INTERNALDATE': datetime.datetime(2011, 1, 30, 13, 32, 9),
        b'RFC822.SIZE': 4567,
        b'SEQ': 84,
        b'ENVELOPE': Envelope(...)
    },
    3293: {
        b'FLAGS': (),
        b'INTERNALDATE': datetime.datetime(2011, 2, 24, 19, 30, 36),
        b'RFC822.SIZE': 8912,
        b'SEQ': 110,
        b'ENVELOPE': Envelope(...)
    }
}
```

**Wichtige Keys:**
- Alle angefragten Data-Items als Keys (z.B. `b'FLAGS'`, `b'ENVELOPE'`)
- `b'SEQ'` - Sequence Number (immer vorhanden)
- Dict-Key selbst = UID (wenn `use_uid=True`)

### Normalise Times

```python
# Standard: normalise_times = True
# Timestamps werden zu Local Time ohne Timezone-Info konvertiert

client.normalise_times = False
# Jetzt: datetime-Objekte mit Timezone-Info (aware)

results = client.fetch([msg_id], ['INTERNALDATE'])
dt = results[msg_id][b'INTERNALDATE']

if client.normalise_times:
    # datetime.datetime(2011, 1, 30, 13, 32, 9) - naive
    pass
else:
    # datetime.datetime(2011, 1, 30, 13, 32, 9, tzinfo=...) - aware
    pass
```

---

## 5. Flags & Labels Management

### Standard IMAP Flags

**System-Flags (mit Backslash):**
- `\Seen` - Gelesen
- `\Answered` - Beantwortet
- `\Flagged` - Markiert/Wichtig
- `\Deleted` - Zur Löschung markiert
- `\Draft` - Entwurf
- `\Recent` - Kürzlich angekommen (Server-managed)

**Custom Flags (ohne Backslash):**
- Beliebige Strings wie `Important`, `NeedsReview`, `AutoClassified`

### Flags abrufen

```python
get_flags(messages)
```

```python
# Flags von bestimmten Nachrichten
flags_dict = client.get_flags([123, 456, 789])
# Rückgabe: {123: (b'\\Seen', b'\\Flagged'), 456: (), 789: (b'\\Seen',)}

for msg_id, flags in flags_dict.items():
    print(f"Message {msg_id}: {flags}")
```

### Flags setzen (überschreibt existierende)

```python
set_flags(messages, flags, silent=False)
```

```python
# Setze als gelesen und wichtig
response = client.set_flags([msg_id], ['\\Seen', '\\Flagged'])
# Rückgabe: {msg_id: (b'\\Seen', b'\\Flagged')} wenn silent=False

# Alle Flags entfernen
response = client.set_flags([msg_id], [])

# Silent-Modus (keine Rückgabe)
client.set_flags([msg_id], ['\\Seen'], silent=True)
# Rückgabe: None
```

### Flags hinzufügen

```python
add_flags(messages, flags, silent=False)
```

```python
# Markiere als wichtig (behält andere Flags)
response = client.add_flags([msg_id], ['\\Flagged'])

# Custom Flag hinzufügen
response = client.add_flags([msg_id], ['AutoClassified'])

# Mehrere Flags auf einmal
response = client.add_flags([msg_id], ['\\Flagged', 'Important', 'NeedsReview'])
```

### Flags entfernen

```python
remove_flags(messages, flags, silent=False)
```

```python
# Entferne "wichtig"-Markierung
response = client.remove_flags([msg_id], ['\\Flagged'])

# Entferne Custom Flag
response = client.remove_flags([msg_id], ['AutoClassified'])
```

### Gmail Labels (Gmail-spezifisch)

Gmail nutzt Labels statt klassische Ordner. Labels funktionieren wie Flags aber mit Hierarchie.

#### Labels abrufen

```python
get_gmail_labels(messages)
```

```python
labels_dict = client.get_gmail_labels([msg_id])
# Rückgabe: {msg_id: (b'\\Important', b'Work/Projects', b'NeedsReview')}
```

#### Labels setzen (überschreibt)

```python
set_gmail_labels(messages, labels, silent=False)
```

```python
# Setze Labels
response = client.set_gmail_labels([msg_id], ['Work/Projects', 'Important'])
```

#### Labels hinzufügen

```python
add_gmail_labels(messages, labels, silent=False)
```

```python
# Label hinzufügen
response = client.add_gmail_labels([msg_id], ['NeedsReview'])

# Hierarchische Labels
response = client.add_gmail_labels([msg_id], ['Work/Projects/AI'])
```

#### Labels entfernen

```python
remove_gmail_labels(messages, labels, silent=False)
```

```python
# Label entfernen
response = client.remove_gmail_labels([msg_id], ['NeedsReview'])
```

### Praktisches Beispiel: Klassifizierungs-System

```python
def classify_and_tag_email(client, msg_id, classification_result):
    """
    Wendet AI-Klassifizierung auf Email an
    
    classification_result = {
        'priority': 'high',     # low, medium, high
        'tags': ['Invoice', 'Customer Support'],
        'action': 'needs_reply' # needs_reply, archive, flag_only
    }
    """
    
    # Gmail-System
    if client.has_capability('X-GM-LABELS'):
        # Tags als Labels
        labels = classification_result['tags']
        
        # Priority als Label
        priority_label = f"Priority/{classification_result['priority'].title()}"
        labels.append(priority_label)
        
        # Action als Label
        action_label = f"Action/{classification_result['action'].replace('_', ' ').title()}"
        labels.append(action_label)
        
        client.add_gmail_labels([msg_id], labels)
    
    # Standard IMAP
    else:
        flags = []
        
        # Priority als Flag
        if classification_result['priority'] == 'high':
            flags.append('\\Flagged')
        
        # Tags als Custom Flags
        for tag in classification_result['tags']:
            flags.append(tag.replace(' ', '_'))
        
        # Action als Flag
        flags.append(classification_result['action'])
        
        client.add_flags([msg_id], flags)
    
    # Als gelesen markieren
    client.add_flags([msg_id], ['\\Seen'])
    
    # Bei Bedarf verschieben
    if classification_result['action'] == 'needs_reply':
        client.move([msg_id], 'NeedsAction')
```

---

## 6. Emails Verschieben & Organisieren

### Nachrichten verschieben

```python
move(messages, folder)
```

**Benötigt:** MOVE Capability (RFC 6851)

```python
# Prüfe ob MOVE unterstützt wird
if client.has_capability('MOVE'):
    # Atomar verschieben (1 Operation)
    response = client.move([msg_id], 'Archive')
else:
    # Fallback: Copy + Delete
    client.copy([msg_id], 'Archive')
    client.delete_messages([msg_id])
    client.expunge()
```

### Nachrichten kopieren

```python
copy(messages, folder)
```

```python
# Nachricht kopieren
response = client.copy([msg_id], 'Backup')
# Original bleibt im aktuellen Ordner

# Mehrere Nachrichten
response = client.copy([123, 456, 789], 'Archive')
```

### Nachrichten löschen

```python
delete_messages(messages, silent=False)
```

```python
# Schritt 1: Zum Löschen markieren
response = client.delete_messages([msg_id])
# Setzt \Deleted Flag

# Schritt 2: Endgültig löschen
response = client.expunge()
# Entfernt alle Nachrichten mit \Deleted Flag
```

### Expunge - Endgültiges Löschen

```python
expunge(messages=None)
```

```python
# ALLE als gelöscht markierten Nachrichten entfernen
response, expunge_list = client.expunge()
# response: Server-Nachricht
# expunge_list: Liste von (seq_num, 'EXPUNGE') Tupeln

# Beispiel-Rückgabe:
# ('Expunge completed.', [(2, 'EXPUNGE'), (1, 'EXPUNGE'), (0, 'RECENT')])

# Nur bestimmte Nachrichten löschen (deprecated, nutze uid_expunge)
response = client.expunge(messages=[123, 456])
```

### UID Expunge (empfohlen)

```python
uid_expunge(messages)
```

**Benötigt:** UIDPLUS Capability

```python
if client.has_capability('UIDPLUS'):
    # Nur bestimmte UIDs löschen
    # Nachrichten müssen bereits \Deleted Flag haben
    response = client.uid_expunge([msg_id])
```

### Nachricht erstellen/hinzufügen

```python
append(folder, msg, flags=(), msg_time=None)
```

```python
from datetime import datetime

# Vollständige Email-Nachricht als String
raw_email = """From: sender@example.com
To: recipient@example.com
Subject: Test Message

This is the body.
"""

# In Ordner einfügen
response = client.append(
    'INBOX',
    raw_email,
    flags=['\\Seen'],
    msg_time=datetime.now()
)

# Ohne Flags und Zeit
response = client.append('Sent', raw_email)
```

### Mehrere Nachrichten auf einmal (MULTIAPPEND)

```python
multiappend(folder, msgs)
```

**Benötigt:** MULTIAPPEND Extension

```python
# msgs ist ein Iterable von Dicts oder Strings
msgs = [
    {
        'msg': raw_email_1,
        'flags': ['\\Seen'],
        'date': datetime.now()
    },
    raw_email_2,  # Nur String ohne Flags/Date
    {
        'msg': raw_email_3,
        'flags': ['\\Flagged']
    }
]

if client.has_capability('MULTIAPPEND'):
    response = client.multiappend('INBOX', msgs)
```

### Workflow-Beispiel: Email nach Klassifizierung organisieren

```python
def organize_classified_email(client, msg_id, classification):
    """
    Organisiert Email basierend auf AI-Klassifizierung
    
    classification = {
        'category': 'Customer Support',
        'priority': 'high',
        'action': 'needs_reply',  # needs_reply, archive, delete
        'confidence': 0.95
    }
    """
    
    # Nur wenn Confidence hoch genug
    if classification['confidence'] < 0.8:
        # In "Review" Ordner für manuelle Prüfung
        if client.has_capability('MOVE'):
            client.move([msg_id], 'NeedsReview')
        return
    
    # Action durchführen
    if classification['action'] == 'needs_reply':
        # In "Action" Ordner
        client.move([msg_id], 'NeedsAction')
        client.add_flags([msg_id], ['\\Flagged'])
        
    elif classification['action'] == 'archive':
        # Archivieren
        client.add_flags([msg_id], ['\\Seen'])
        category_folder = f"Archive/{classification['category']}"
        
        # Ordner erstellen falls nicht vorhanden
        if not client.folder_exists(category_folder):
            client.create_folder(category_folder)
        
        client.move([msg_id], category_folder)
        
    elif classification['action'] == 'delete':
        # Sicher in Trash verschieben
        trash = client.find_special_folder(imapclient.TRASH)
        if trash:
            client.move([msg_id], trash)
        else:
            # Fallback: Direkt löschen
            client.delete_messages([msg_id])
            client.expunge()
```

---

## 7. IDLE - Echtzeit-Monitoring

IDLE ermöglicht Echtzeit-Benachrichtigungen über Änderungen im ausgewählten Ordner.

### IDLE starten

```python
idle()
```

```python
# Prüfe ob Server IDLE unterstützt
if not client.has_capability('IDLE'):
    print("Server unterstützt kein IDLE")
    # Fallback zu Polling
    
# Ordner auswählen
client.select_folder('INBOX')

# IDLE-Modus aktivieren
client.idle()
print("IDLE-Modus aktiv, warte auf Änderungen...")
```

**WICHTIG:** Im IDLE-Modus können KEINE anderen Befehle ausgeführt werden!

### Auf IDLE-Responses warten

```python
idle_check(timeout=None)
```

```python
# Blockiert bis Response kommt
responses = client.idle_check()

# Mit Timeout (in Sekunden)
responses = client.idle_check(timeout=30)

# Rückgabe: Liste von Responses
# Beispiele:
# [(b'OK', b'Still here')]
# [(1, b'EXISTS')]
# [(1, b'FETCH', (b'FLAGS', (b'\\Seen',)))]
# [(5, b'EXISTS'), (1, b'RECENT')]
```

**Mögliche IDLE-Responses:**
- `(n, b'EXISTS')` - Neue Nachricht(en), n = neue Gesamtanzahl
- `(n, b'RECENT')` - Kürzlich eingetroffen
- `(n, b'EXPUNGE')` - Nachricht n wurde gelöscht
- `(n, b'FETCH', ...)` - Flags einer Nachricht geändert
- `(b'OK', message)` - Server-Keepalive

### IDLE beenden

```python
idle_done()
```

```python
# IDLE-Modus beenden
command_text, idle_responses = client.idle_done()

# command_text: z.B. b'Idle terminated'
# idle_responses: Alle Responses seit letztem idle_check()
```

### Praktisches IDLE-Beispiel: Live-Klassifizierung

```python
import threading
import time

def idle_monitoring(client):
    """
    Kontinuierliches Monitoring mit IDLE
    """
    
    if not client.has_capability('IDLE'):
        print("IDLE nicht unterstützt, verwende Polling")
        return polling_monitoring(client)
    
    client.select_folder('INBOX')
    
    while True:
        try:
            # IDLE starten
            client.idle()
            print("Warte auf neue Emails...")
            
            # Warte max 29 Minuten (IDLE-Timeout ist oft 30 Min)
            responses = client.idle_check(timeout=29*60)
            
            # IDLE beenden
            client.idle_done()
            
            # Responses verarbeiten
            for response in responses:
                if len(response) >= 2 and response[1] == b'EXISTS':
                    # Neue Nachricht(en)
                    print(f"Neue Nachricht! Anzahl jetzt: {response[0]}")
                    
                    # Neue Nachrichten klassifizieren
                    process_new_messages(client)
                    
                elif len(response) >= 2 and response[1] == b'FETCH':
                    # Flag-Änderung
                    msg_seq = response[0]
                    print(f"Nachricht {msg_seq} wurde geändert")
            
            # Kurze Pause bevor IDLE neu gestartet wird
            time.sleep(1)
            
        except KeyboardInterrupt:
            print("Monitoring beendet")
            break
        except Exception as e:
            print(f"Fehler: {e}")
            time.sleep(5)  # Pause bei Fehler

def process_new_messages(client):
    """
    Verarbeitet neue ungelesene Nachrichten
    """
    unseen = client.search(['UNSEEN'])
    
    if not unseen:
        return
    
    # Metadaten abrufen
    results = client.fetch(unseen, ['FLAGS', 'ENVELOPE', 'BODY.PEEK[TEXT]'])
    
    for msg_id, data in results.items():
        envelope = data[b'ENVELOPE']
        body = data.get(b'BODY[TEXT]', b'').decode('utf-8', errors='ignore')
        
        # AI-Klassifizierung
        classification = classify_with_ai(envelope, body)
        
        # Organisieren
        organize_classified_email(client, msg_id, classification)

def polling_monitoring(client):
    """
    Fallback wenn IDLE nicht verfügbar
    """
    client.select_folder('INBOX')
    last_uid = 0
    
    while True:
        try:
            # Suche nach neuen UIDs
            all_uids = client.search(['ALL'])
            
            if all_uids:
                max_uid = max(all_uids)
                
                if max_uid > last_uid:
                    # Neue Nachrichten seit letztem Check
                    new_uids = [uid for uid in all_uids if uid > last_uid]
                    print(f"{len(new_uids)} neue Nachricht(en)")
                    
                    process_new_messages(client)
                    last_uid = max_uid
            
            # 60 Sekunden warten
            time.sleep(60)
            
        except KeyboardInterrupt:
            print("Monitoring beendet")
            break
        except Exception as e:
            print(f"Fehler: {e}")
            time.sleep(5)

# Verwendung
with IMAPClient('imap.gmail.com') as client:
    client.login('user@gmail.com', 'password')
    idle_monitoring(client)
```

### IDLE mit Threading

```python
class EmailMonitor:
    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password
        self.running = False
        self.client = None
        self.thread = None
    
    def start(self):
        """Startet Monitoring in separatem Thread"""
        self.running = True
        self.thread = threading.Thread(target=self._monitor)
        self.thread.start()
    
    def stop(self):
        """Stoppt Monitoring"""
        self.running = False
        if self.thread:
            self.thread.join()
    
    def _monitor(self):
        """Monitoring-Loop"""
        with IMAPClient(self.host) as client:
            client.login(self.username, self.password)
            self.client = client
            
            client.select_folder('INBOX')
            
            while self.running:
                try:
                    if client.has_capability('IDLE'):
                        client.idle()
                        responses = client.idle_check(timeout=30)
                        client.idle_done()
                        
                        for response in responses:
                            if len(response) >= 2 and response[1] == b'EXISTS':
                                self.on_new_message()
                    else:
                        time.sleep(60)
                        self.check_for_new_messages()
                        
                except Exception as e:
                    print(f"Monitoring-Fehler: {e}")
                    time.sleep(5)
    
    def on_new_message(self):
        """Callback bei neuer Nachricht"""
        print("Neue Nachricht erkannt!")
        # Deine Logik hier
    
    def check_for_new_messages(self):
        """Polling-Methode"""
        unseen = self.client.search(['UNSEEN'])
        if unseen:
            self.on_new_message()

# Verwendung
monitor = EmailMonitor('imap.gmail.com', 'user@gmail.com', 'password')
monitor.start()

# Läuft jetzt im Hintergrund
# ...dein restlicher Code...

# Zum Beenden
monitor.stop()
```

---

## 8. Gmail-Spezifische Features

### Gmail Labels

Gmail nutzt Labels statt traditionelle Ordner-Struktur. Labels können hierarchisch sein.

```python
# Labels hinzufügen/entfernen
client.add_gmail_labels([msg_id], ['Work/Projects', 'Important'])
client.remove_gmail_labels([msg_id], ['Inbox'])

# Labels abrufen
labels = client.get_gmail_labels([msg_id])
# Rückgabe: {msg_id: (b'Work/Projects', b'Important')}

# Labels setzen (überschreibt)
client.set_gmail_labels([msg_id], ['Archive', 'Read'])
```

### Gmail Suche (X-GM-RAW)

```python
# Gmail-Syntax nutzen
results = client.gmail_search('has:attachment in:unread')
results = client.gmail_search('from:mike@example.com subject:important')
results = client.gmail_search('is:starred -is:read')
results = client.gmail_search('larger:5M newer_than:7d')
results = client.gmail_search('label:work OR label:personal')
```

### Gmail Message & Thread IDs

```python
# Fetch Gmail-spezifische IDs
results = client.fetch([msg_id], ['X-GM-MSGID', 'X-GM-THRID', 'X-GM-LABELS'])

msg_data = results[msg_id]
gmail_msgid = msg_data[b'X-GM-MSGID']    # Unveränderliche Message-ID
gmail_thrid = msg_data[b'X-GM-THRID']    # Thread-ID
gmail_labels = msg_data[b'X-GM-LABELS']  # Tuple von Labels
```

### Spezielle Gmail-Ordner

```python
# Gmail hat spezielle "Ordner" (eigentlich Labels)
gmail_folders = [
    '[Gmail]/All Mail',      # Alle Nachrichten
    '[Gmail]/Sent Mail',     # Gesendet
    '[Gmail]/Drafts',        # Entwürfe
    '[Gmail]/Spam',          # Spam
    '[Gmail]/Trash',         # Papierkorb
    '[Gmail]/Starred',       # Markiert
    '[Gmail]/Important',     # Wichtig
]

# Achtung: Namen können lokalisiert sein!
# Besser: find_special_folder nutzen
sent = client.find_special_folder(imapclient.SENT)
```

### Gmail-Workflow-Beispiel

```python
def classify_gmail_email(client, msg_id):
    """
    Klassifiziert und organisiert Gmail-Nachricht
    """
    # Gmail-Daten abrufen
    results = client.fetch(
        [msg_id], 
        ['ENVELOPE', 'X-GM-LABELS', 'X-GM-THRID', 'BODY.PEEK[TEXT]']
    )
    
    data = results[msg_id]
    envelope = data[b'ENVELOPE']
    current_labels = data[b'X-GM-LABELS']
    thread_id = data[b'X-GM-THRID']
    body = data.get(b'BODY[TEXT]', b'').decode('utf-8', errors='ignore')
    
    # AI-Klassifizierung
    classification = classify_with_ai(envelope, body)
    
    # Labels basierend auf Klassifizierung
    new_labels = []
    
    # Kategorie als Label
    category = classification['category'].replace(' ', '_')
    new_labels.append(f'Auto/{category}')
    
    # Priority
    priority = classification['priority']
    if priority == 'high':
        new_labels.append('Priority/High')
    elif priority == 'medium':
        new_labels.append('Priority/Medium')
    
    # Sentiment (falls vorhanden)
    if 'sentiment' in classification:
        sentiment = classification['sentiment']
        new_labels.append(f'Sentiment/{sentiment.title()}')
    
    # Labels hinzufügen
    client.add_gmail_labels([msg_id], new_labels)
    
    # Aus Inbox entfernen wenn archiviert werden soll
    if classification['action'] == 'archive':
        client.remove_gmail_labels([msg_id], ['\\Inbox'])
    
    # Als wichtig markieren wenn Priority high
    if priority == 'high':
        client.add_gmail_labels([msg_id], ['\\Important'])
```

---

## 9. Error Handling & Exceptions

### Exception-Hierarchie

```python
# Basis-Exception
IMAPClientError

# Schwerwiegender Fehler - Verbindung nicht mehr nutzbar
IMAPClientAbortError

# Read-only Ordner
IMAPClientReadOnlyError
```

### Spezifische Exceptions

```python
from imapclient.exceptions import (
    IMAPClientError,
    IMAPClientAbortError,
    IMAPClientReadOnlyError,
    CapabilityError,
    IllegalStateError,
    InvalidCriteriaError,
    LoginError,
    ProtocolError
)
```

**Exception-Typen:**

- `CapabilityError` - Benötigte Capability nicht vorhanden
- `IllegalStateError` - Befehl benötigt anderen State (z.B. nicht eingeloggt, kein Ordner ausgewählt)
- `InvalidCriteriaError` - Fehler in Such-Kriterien
- `LoginError` - Authentifizierung fehlgeschlagen
- `ProtocolError` - Server-Response verletzt IMAP-Protokoll

### Niedrigere Layer-Exceptions

```python
import socket
import ssl

# Netzwerk-Fehler
socket.error
socket.timeout

# SSL/TLS-Fehler
ssl.SSLError
ssl.CertificateError  # Keine Subclass von SSLError!
```

### Praktisches Error Handling

```python
from imapclient import IMAPClient
from imapclient.exceptions import (
    IMAPClientError,
    IMAPClientAbortError,
    LoginError,
    IllegalStateError
)
import socket
import ssl
import time

def safe_imap_operation(host, username, password):
    """
    Robuste IMAP-Verbindung mit Error Handling
    """
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        client = None
        try:
            # Verbindung mit Timeout
            timeout = SocketTimeout(connect=15, read=60)
            client = IMAPClient(host, timeout=timeout)
            
            # Login
            try:
                client.login(username, password)
            except LoginError as e:
                print(f"Login fehlgeschlagen: {e}")
                return None  # Keine Retries bei falschen Credentials
            
            # Ordner auswählen
            try:
                info = client.select_folder('INBOX')
            except IllegalStateError as e:
                print(f"Kann Ordner nicht auswählen: {e}")
                return None
            
            # Operationen durchführen
            try:
                messages = client.search(['UNSEEN'])
                
                if messages:
                    results = client.fetch(messages, ['FLAGS', 'ENVELOPE'])
                    process_messages(results)
                    
            except IMAPClientAbortError as e:
                # Schwerwiegender Fehler - Verbindung tot
                print(f"Verbindung abgebrochen: {e}")
                client = None  # Nicht versuchen zu schließen
                raise  # Für äußeres Retry
            
            except IMAPClientError as e:
                # Allgemeiner IMAP-Fehler
                print(f"IMAP-Fehler: {e}")
                # Kann möglicherweise recovered werden
                
            return client
            
        except socket.timeout:
            print(f"Timeout bei Versuch {attempt + 1}/{max_retries}")
            time.sleep(retry_delay)
            
        except socket.error as e:
            print(f"Netzwerkfehler bei Versuch {attempt + 1}/{max_retries}: {e}")
            time.sleep(retry_delay)
            
        except ssl.SSLError as e:
            print(f"SSL-Fehler: {e}")
            return None  # Keine Retries bei SSL-Problemen
            
        except ssl.CertificateError as e:
            print(f"Zertifikatfehler: {e}")
            return None
            
        except Exception as e:
            print(f"Unerwarteter Fehler: {e}")
            time.sleep(retry_delay)
            
        finally:
            # Cleanup bei Fehler
            if client is not None:
                try:
                    client.logout()
                except:
                    pass  # Bei Fehler beim Logout nicht noch mehr Fehler werfen
    
    print(f"Alle {max_retries} Versuche fehlgeschlagen")
    return None

# Verwendung
def main():
    client = safe_imap_operation('imap.gmail.com', 'user@gmail.com', 'password')
    
    if client:
        try:
            # Arbeite mit client
            pass
        finally:
            client.logout()

### Spezifische Error-Situationen

```python
# Capability prüfen bevor Feature genutzt wird
if not client.has_capability('MOVE'):
    # Fallback
    client.copy([msg_id], 'Archive')
    client.delete_messages([msg_id])
    client.expunge()
else:
    client.move([msg_id], 'Archive')

# Read-only Ordner
try:
    client.select_folder('INBOX', readonly=False)
    client.add_flags([msg_id], ['\\Seen'])
except IMAPClientReadOnlyError:
    print("Ordner ist read-only")
    # Ordner neu in read-write öffnen
    client.select_folder('INBOX', readonly=False)

# Invalid Search Criteria
try:
    results = client.search(['INVALID_CRITERION'])
except InvalidCriteriaError as e:
    print(f"Ungültige Such-Kriterien: {e}")

# Ordner existiert nicht
if client.folder_exists('Work/Projects'):
    client.select_folder('Work/Projects')
else:
    client.create_folder('Work/Projects')
    client.select_folder('Work/Projects')
```

---

## 10. Performance & Best Practices

### 1. Batch-Operations

```python
# SCHLECHT: Einzelne Operationen
for msg_id in msg_ids:
    client.add_flags([msg_id], ['\\Seen'])  # 1000 Roundtrips!

# GUT: Batch-Operation
client.add_flags(msg_ids, ['\\Seen'])  # 1 Roundtrip
```

### 2. folder_status() statt select_folder()

```python
# SCHLECHT: Ordner wechseln nur für Stats
for folder in folders:
    info = client.select_folder(folder)
    print(f"{folder}: {info[b'EXISTS']} messages")

# GUT: folder_status nutzen
for folder in folders:
    status = client.folder_status(folder, ['MESSAGES'])
    print(f"{folder}: {status[b'MESSAGES']} messages")
```

### 3. BODY.PEEK statt BODY

```python
# SCHLECHT: Setzt \Seen Flag
results = client.fetch(msg_ids, ['BODY[]'])

# GUT: Setzt Flag NICHT
results = client.fetch(msg_ids, ['BODY.PEEK[]'])
```

### 4. Nur benötigte Daten abrufen

```python
# SCHLECHT: Alles abrufen
results = client.fetch(msg_ids, ['RFC822'])  # Komplette Email

# GUT: Nur Metadaten für Klassifizierung
results = client.fetch(msg_ids, ['FLAGS', 'ENVELOPE', 'RFC822.SIZE'])
```

### 5. use_uid=True (Standard)

```python
# GUT: UIDs sind stabil
client = IMAPClient('imap.gmail.com', use_uid=True)  # Standard

# Sequence Numbers ändern sich bei Löschungen
# UIDs bleiben gleich
```

### 6. Context Manager nutzen

```python
# GUT: Automatisches Cleanup
with IMAPClient('imap.gmail.com') as client:
    client.login('user', 'pass')
    # ...
    # logout() wird automatisch aufgerufen
```

### 7. Connection Pooling für High-Volume

```python
from queue import Queue
import threading

class IMAPConnectionPool:
    def __init__(self, host, username, password, pool_size=5):
        self.host = host
        self.username = username
        self.password = password
        self.pool = Queue(maxsize=pool_size)
        
        # Pool füllen
        for _ in range(pool_size):
            client = IMAPClient(host)
            client.login(username, password)
            self.pool.put(client)
    
    def get_connection(self):
        """Hole Verbindung aus Pool"""
        return self.pool.get()
    
    def return_connection(self, client):
        """Gib Verbindung zurück in Pool"""
        self.pool.put(client)
    
    def close_all(self):
        """Schließe alle Verbindungen"""
        while not self.pool.empty():
            client = self.pool.get()
            try:
                client.logout()
            except:
                pass

# Verwendung
pool = IMAPConnectionPool('imap.gmail.com', 'user', 'pass', pool_size=5)

def process_mailbox(folder):
    client = pool.get_connection()
    try:
        client.select_folder(folder)
        messages = client.search(['UNSEEN'])
        # ... verarbeite messages ...
    finally:
        pool.return_connection(client)

# Multi-threaded Processing
threads = []
for folder in ['INBOX', 'Work', 'Personal']:
    t = threading.Thread(target=process_mailbox, args=(folder,))
    t.start()
    threads.append(t)

for t in threads:
    t.join()

pool.close_all()
```

### 8. Paginierung für große Mailboxen

```python
def process_mailbox_paginated(client, folder, batch_size=100):
    """
    Verarbeitet große Mailboxen in Batches
    """
    client.select_folder(folder)
    
    # Alle UIDs holen
    all_uids = client.search(['ALL'])
    
    print(f"Verarbeite {len(all_uids)} Nachrichten in Batches von {batch_size}")
    
    # In Batches verarbeiten
    for i in range(0, len(all_uids), batch_size):
        batch = all_uids[i:i+batch_size]
        
        print(f"Batch {i//batch_size + 1}: UIDs {batch[0]}-{batch[-1]}")
        
        # Fetch Batch
        results = client.fetch(batch, ['FLAGS', 'ENVELOPE'])
        
        # Verarbeite Batch
        for msg_id, data in results.items():
            process_message(msg_id, data)
        
        # Optional: Pause zwischen Batches
        time.sleep(0.1)
```

### 9. IDLE vs Polling

```python
# IDLE: Für Echtzeit (wenn unterstützt)
if client.has_capability('IDLE'):
    # Server benachrichtigt sofort
    client.idle()
    responses = client.idle_check(timeout=29*60)
    client.idle_done()
else:
    # Polling: Nur wenn IDLE nicht verfügbar
    time.sleep(60)  # 1 Minute warten
    new = client.search(['UNSEEN'])
```

### 10. Caching von Capabilities & Namespaces

```python
class CachedIMAPClient:
    def __init__(self, host, username, password):
        self.client = IMAPClient(host)
        self.client.login(username, password)
        
        # Cache bei Initialisierung
        self._capabilities = self.client.capabilities()
        self._namespaces = self.client.namespace()
        self._folders_cache = {}
        self._last_folder_update = 0
    
    def has_capability(self, cap):
        return cap.encode() in self._capabilities
    
    def get_folders(self, force_refresh=False):
        """Cached folder list"""
        now = time.time()
        
        if force_refresh or (now - self._last_folder_update) > 300:  # 5 Min
            self._folders_cache = self.client.list_folders()
            self._last_folder_update = now
        
        return self._folders_cache
```

---

## 11. Komplette Workflow-Beispiele

### Beispiel 1: Email-Klassifizierungs-System

```python
#!/usr/bin/env python3
"""
Automatisches Email-Klassifizierungs-System mit KI
"""

from imapclient import IMAPClient
from datetime import datetime, timedelta
import json
import time

class EmailClassificationSystem:
    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password
        self.client = None
        
    def connect(self):
        """Stelle Verbindung her"""
        self.client = IMAPClient(self.host)
        self.client.login(self.username, self.password)
        print(f"Verbunden mit {self.host}")
        
        # Prüfe Capabilities
        if self.client.has_capability('IDLE'):
            print("✓ IDLE unterstützt")
        if self.client.has_capability('MOVE'):
            print("✓ MOVE unterstützt")
        if self.client.has_capability('X-GM-LABELS'):
            print("✓ Gmail Labels unterstützt")
    
    def disconnect(self):
        """Trenne Verbindung"""
        if self.client:
            self.client.logout()
            print("Verbindung getrennt")
    
    def classify_email(self, envelope, body_text):
        """
        Simulierte KI-Klassifizierung
        In Produktion: API-Aufruf zu KI-Service
        """
        # Vereinfachte Klassifizierung basierend auf Keywords
        subject = envelope.subject.decode('utf-8', errors='ignore').lower()
        sender = ""
        if envelope.from_ and len(envelope.from_) > 0:
            sender_addr = envelope.from_[0]
            sender = f"{sender_addr.mailbox.decode()}@{sender_addr.host.decode()}"
        
        body_lower = body_text.lower()
        
        # Kategorisierung
        category = 'General'
        if 'rechnung' in subject or 'invoice' in subject:
            category = 'Finance'
        elif 'meeting' in subject or 'termin' in subject:
            category = 'Meetings'
        elif 'support' in subject or 'hilfe' in subject:
            category = 'Customer Support'
        
        # Priorität
        priority = 'medium'
        urgent_keywords = ['urgent', 'dringend', 'asap', 'wichtig', 'important']
        if any(kw in subject or kw in body_lower for kw in urgent_keywords):
            priority = 'high'
        
        # Action
        action = 'archive'
        if priority == 'high':
            action = 'needs_reply'
        elif 'frage' in subject or '?' in subject:
            action = 'needs_reply'
        
        return {
            'category': category,
            'priority': priority,
            'action': action,
            'confidence': 0.85,
            'tags': [category, f'Priority-{priority.title()}']
        }
    
    def organize_email(self, msg_id, classification):
        """Organisiert Email basierend auf Klassifizierung"""
        
        # Gmail-System
        if self.client.has_capability('X-GM-LABELS'):
            labels = []
            
            # Auto-Label als Prefix
            for tag in classification['tags']:
                labels.append(f'Auto/{tag}')
            
            # Labels setzen
            self.client.add_gmail_labels([msg_id], labels)
            
            # Aus Inbox entfernen wenn archiviert
            if classification['action'] == 'archive':
                self.client.remove_gmail_labels([msg_id], ['\\Inbox'])
            
            # Als wichtig markieren
            if classification['priority'] == 'high':
                self.client.add_gmail_labels([msg_id], ['\\Important'])
        
        # Standard IMAP
        else:
            flags = []
            
            # Priority als Flag
            if classification['priority'] == 'high':
                flags.append('\\Flagged')
            
            # Tags als Custom Flags
            for tag in classification['tags']:
                flags.append(tag.replace(' ', '_'))
            
            self.client.add_flags([msg_id], flags)
            
            # In Ziel-Ordner verschieben
            target_folder = f'Auto/{classification["category"]}'
            
            # Ordner erstellen falls nötig
            if not self.client.folder_exists(target_folder):
                self.client.create_folder(target_folder)
            
            # Verschieben
            if self.client.has_capability('MOVE'):
                self.client.move([msg_id], target_folder)
            else:
                self.client.copy([msg_id], target_folder)
                self.client.delete_messages([msg_id])
                self.client.expunge()
        
        # Als gelesen markieren
        self.client.add_flags([msg_id], ['\\Seen'])
    
    def process_folder(self, folder='INBOX'):
        """Verarbeite alle ungelesenen Emails in einem Ordner"""
        print(f"\n=== Verarbeite Ordner: {folder} ===")
        
        # Ordner auswählen
        info = self.client.select_folder(folder)
        print(f"Ordner hat {info[b'EXISTS']} Nachrichten")
        
        # Ungelesene Nachrichten finden
        unseen = self.client.search(['UNSEEN'])
        
        if not unseen:
            print("Keine ungelesenen Nachrichten")
            return
        
        print(f"Verarbeite {len(unseen)} ungelesene Nachrichten...")
        
        # In Batches von 50 verarbeiten
        batch_size = 50
        for i in range(0, len(unseen), batch_size):
            batch = unseen[i:i+batch_size]
            
            # Daten abrufen (mit PEEK um nicht als gelesen zu markieren)
            results = self.client.fetch(
                batch, 
                ['FLAGS', 'ENVELOPE', 'RFC822.SIZE', 'BODY.PEEK[TEXT]']
            )
            
            for msg_id, data in results.items():
                try:
                    envelope = data[b'ENVELOPE']
                    body = data.get(b'BODY[TEXT]', b'').decode('utf-8', errors='ignore')
                    size = data[b'RFC822.SIZE']
                    
                    # Absender extrahieren
                    sender = "Unknown"
                    if envelope.from_ and len(envelope.from_) > 0:
                        sender_addr = envelope.from_[0]
                        sender = f"{sender_addr.mailbox.decode()}@{sender_addr.host.decode()}"
                    
                    # Betreff extrahieren
                    subject = envelope.subject.decode('utf-8', errors='ignore') if envelope.subject else "(kein Betreff)"
                    
                    print(f"\n[{msg_id}] Von: {sender}")
                    print(f"  Betreff: {subject}")
                    print(f"  Größe: {size} bytes")
                    
                    # Klassifizierung
                    classification = self.classify_email(envelope, body)
                    
                    print(f"  → Kategorie: {classification['category']}")
                    print(f"  → Priorität: {classification['priority']}")
                    print(f"  → Action: {classification['action']}")
                    print(f"  → Confidence: {classification['confidence']:.2f}")
                    
                    # Organisieren
                    if classification['confidence'] >= 0.7:
                        self.organize_email(msg_id, classification)
                        print(f"  ✓ Organisiert")
                    else:
                        print(f"  ⚠ Confidence zu niedrig, übersprungen")
                
                except Exception as e:
                    print(f"  ✗ Fehler bei Message {msg_id}: {e}")
    
    def monitor_inbox(self):
        """Kontinuierliches Monitoring mit IDLE"""
        print("\n=== Starte Inbox-Monitoring ===")
        
        if not self.client.has_capability('IDLE'):
            print("IDLE nicht unterstützt, verwende Polling")
            self.monitor_inbox_polling()
            return
        
        self.client.select_folder('INBOX')
        
        while True:
            try:
                # IDLE starten
                self.client.idle()
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Warte auf neue Emails...")
                
                # Warte auf Änderungen (max 29 Min)
                responses = self.client.idle_check(timeout=29*60)
                
                # IDLE beenden
                self.client.idle_done()
                
                # Responses verarbeiten
                new_messages = False
                for response in responses:
                    if len(response) >= 2 and response[1] == b'EXISTS':
                        new_messages = True
                        print(f"✉ Neue Nachricht(en)! Anzahl: {response[0]}")
                
                if new_messages:
                    self.process_folder('INBOX')
                
                # Kurze Pause
                time.sleep(1)
                
            except KeyboardInterrupt:
                print("\n\nMonitoring beendet")
                break
            except Exception as e:
                print(f"Fehler: {e}")
                time.sleep(5)
    
    def monitor_inbox_polling(self):
        """Polling-basiertes Monitoring (Fallback)"""
        last_uid = 0
        self.client.select_folder('INBOX')
        
        while True:
            try:
                all_uids = self.client.search(['ALL'])
                
                if all_uids:
                    max_uid = max(all_uids)
                    
                    if max_uid > last_uid:
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Neue Nachrichten erkannt")
                        self.process_folder('INBOX')
                        last_uid = max_uid
                
                # 60 Sekunden warten
                time.sleep(60)
                
            except KeyboardInterrupt:
                print("\n\nMonitoring beendet")
                break
            except Exception as e:
                print(f"Fehler: {e}")
                time.sleep(5)
    
    def generate_report(self):
        """Generiert Statistik-Report"""
        print("\n=== Email-Statistiken ===")
        
        folders = self.client.list_folders()
        
        stats = {
            'total_messages': 0,
            'unread_messages': 0,
            'folders': {}
        }
        
        for flags, delimiter, folder_name in folders:
            try:
                status = self.client.folder_status(
                    folder_name, 
                    ['MESSAGES', 'UNSEEN']
                )
                
                total = status[b'MESSAGES']
                unread = status[b'UNSEEN']
                
                stats['total_messages'] += total
                stats['unread_messages'] += unread
                stats['folders'][folder_name] = {
                    'total': total,
                    'unread': unread
                }
                
                if unread > 0:
                    print(f"\n{folder_name}:")
                    print(f"  Total: {total}")
                    print(f"  Ungelesen: {unread}")
                    
            except Exception as e:
                print(f"Fehler bei {folder_name}: {e}")
        
        print(f"\n{'='*50}")
        print(f"Gesamt: {stats['total_messages']} Nachrichten")
        print(f"Ungelesen: {stats['unread_messages']}")
        
        return stats

def main():
    """Hauptprogramm"""
    import sys
    
    # Konfiguration (in Produktion aus Config-File/Env laden)
    HOST = 'imap.gmail.com'
    USERNAME = 'user@gmail.com'
    PASSWORD = 'app-password'  # App-Password bei 2FA!
    
    # System initialisieren
    system = EmailClassificationSystem(HOST, USERNAME, PASSWORD)
    
    try:
        # Verbinden
        system.connect()
        
        if len(sys.argv) > 1:
            command = sys.argv[1]
            
            if command == 'process':
                # Einmalige Verarbeitung
                system.process_folder('INBOX')
            
            elif command == 'monitor':
                # Kontinuierliches Monitoring
                system.monitor_inbox()
            
            elif command == 'report':
                # Statistik-Report
                system.generate_report()
            
            else:
                print(f"Unbekannter Befehl: {command}")
                print("Verfügbare Befehle: process, monitor, report")
        
        else:
            # Standard: Report + einmalige Verarbeitung
            system.generate_report()
            system.process_folder('INBOX')
    
    except KeyboardInterrupt:
        print("\n\nBeendet durch Benutzer")
    
    except Exception as e:
        print(f"\nFehler: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Verbindung trennen
        system.disconnect()

if __name__ == '__main__':
    main()
```

**Verwendung:**
```bash
# Einmalige Verarbeitung
python email_classifier.py process

# Kontinuierliches Monitoring
python email_classifier.py monitor

# Statistik-Report
python email_classifier.py report
```

---

## Anhang: Schnellreferenz

### Häufigste Operationen

```python
# Verbinden
with IMAPClient('imap.gmail.com') as client:
    client.login('user@gmail.com', 'password')
    
    # Ordner auswählen
    client.select_folder('INBOX')
    
    # Ungelesene finden
    unseen = client.search(['UNSEEN'])
    
    # Daten abrufen
    results = client.fetch(unseen, ['FLAGS', 'ENVELOPE'])
    
    # Als gelesen markieren
    client.add_flags(unseen, ['\\Seen'])
    
    # Verschieben
    client.move(unseen, 'Archive')
```

### Wichtigste Daten-Selektoren für FETCH

```python
# Metadaten
['FLAGS', 'ENVELOPE', 'RFC822.SIZE', 'INTERNALDATE']

# Mit Body für AI-Analyse
['ENVELOPE', 'BODY.PEEK[TEXT]', 'FLAGS']

# Gmail-spezifisch
['X-GM-LABELS', 'X-GM-MSGID', 'X-GM-THRID', 'ENVELOPE']

# Komplette Email
['RFC822']  # oder ['BODY.PEEK[]'] ohne \Seen zu setzen
```

### Wichtigste Such-Kriterien

```python
['UNSEEN']                          # Ungelesen
['FLAGGED']                         # Markiert
['SINCE', date(2024, 1, 1)]         # Seit Datum
['FROM', 'mike@example.com']        # Von Absender
['SUBJECT', 'wichtig']              # Betreff enthält
['TEXT', 'keyword']                 # Body oder Betreff
['LARGER', 1000000]                 # Größer als 1MB
['NOT', 'DELETED']                  # Nicht gelöscht
['OR', 'FLAGGED', 'UNSEEN']         # Wichtig ODER ungelesen
```

---

**Ende des Handbuchs**

Dieses Handbuch deckt alle wichtigen Aspekte von IMAPClient für ein Email-Klassifizierungs-System ab. Für weitere Details siehe die offizielle Dokumentation: https://imapclient.readthedocs.io/
