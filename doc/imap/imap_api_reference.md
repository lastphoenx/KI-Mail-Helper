# IMAP API Referenz für Email-Klassifizierung

## 1. Verbindung & Authentifizierung

```python
from imapclient import IMAPClient

# Verbindung aufbauen
server = IMAPClient('imap.example.com', ssl=True, port=993)
server.login('username', 'password')

# Alternativ mit OAuth2
server.oauth2_login('username', 'access_token')

# Verbindung beenden
server.logout()
```

## 2. Ordner-Operationen

### a) Alle Ordner auflisten

```python
# Alle Ordner rekursiv auflisten
folders = server.list_folders()
# Rückgabe: Liste von (flags, delimiter, name) Tuples
# Beispiel: [(b'\\HasNoChildren', '/', 'INBOX'), (b'\\HasChildren', '/', 'Work')]

# Nur Unterordner eines bestimmten Verzeichnisses
folders = server.list_folders(directory='INBOX', pattern='*')

# Nur abonnierte Ordner
subscribed = server.list_sub_folders()

# Namespaces abrufen (für komplexere Strukturen)
namespaces = server.namespace()
# Rückgabe: NamespaceResponse mit personal, other_users, shared
```

### Ordner auswählen

```python
# Ordner zum Lesen auswählen
select_info = server.select_folder('INBOX')
# Rückgabe: Dictionary mit Infos wie EXISTS, RECENT, UIDVALIDITY, FLAGS

# Read-only Modus (keine Änderungen möglich)
select_info = server.select_folder('INBOX', readonly=True)
```

## 3. Mail-Anzahl & Status pro Ordner

### c) Zusammenfassung der Mail-Anzahl

```python
# Methode 1: Nach SELECT
info = server.select_folder('INBOX')
total_messages = info[b'EXISTS']
recent_messages = info[b'RECENT']

# Methode 2: Mit STATUS (ohne Ordner zu wechseln)
status = server.folder_status('INBOX', ['MESSAGES', 'RECENT', 'UNSEEN', 'UIDNEXT'])
# Rückgabe: {b'MESSAGES': 1234, b'RECENT': 5, b'UNSEEN': 42, b'UIDNEXT': 5678}

# Für mehrere Ordner iterieren
folder_stats = {}
for flags, delimiter, name in server.list_folders():
    try:
        status = server.folder_status(name, ['MESSAGES', 'UNSEEN'])
        folder_stats[name] = {
            'total': status[b'MESSAGES'],
            'unread': status[b'UNSEEN']
        }
    except:
        pass  # Ordner nicht zugänglich
```

## 4. Nachrichten abrufen & durchsuchen

### Nach UIDs suchen

```python
# Alle Nachrichten im aktuellen Ordner
messages = server.search()
# Rückgabe: Liste von Message UIDs

# Nur ungelesene Nachrichten
unseen = server.search(['UNSEEN'])

# Komplexere Suche
criteria = ['UNSEEN', 'FROM', 'mike@example.com', 'SINCE', '01-Jan-2024']
results = server.search(criteria)

# Mit Gmail-spezifischen Operatoren
gmail_search = server.gmail_search('is:unread subject:wichtig')
```

### Nachrichten-Metadaten abrufen

```python
# FETCH für bestimmte Felder
messages = server.search(['ALL'])
fetch_data = server.fetch(messages, ['FLAGS', 'ENVELOPE', 'RFC822.SIZE', 'INTERNALDATE'])

# Beispiel-Rückgabe:
# {
#   123: {
#     b'FLAGS': (b'\\Seen',),
#     b'ENVELOPE': Envelope(...),
#     b'RFC822.SIZE': 4567,
#     b'INTERNALDATE': datetime(...)
#   }
# }

# Nur Header abrufen
headers = server.fetch(messages, ['BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)]'])

# Vollständige Nachricht
full_msg = server.fetch([msg_id], ['RFC822'])
```

## 5. Flags & Status verwalten

### b) & d) Flags auflisten und setzen

```python
# Standard IMAP Flags:
# \\Seen       - Gelesen
# \\Answered   - Beantwortet
# \\Flagged    - Markiert/Wichtig
# \\Deleted    - Zur Löschung markiert
# \\Draft      - Entwurf
# \\Recent     - Neu im Ordner

# Flags einer Nachricht abrufen
fetch_data = server.fetch([msg_id], ['FLAGS'])
current_flags = fetch_data[msg_id][b'FLAGS']

# Flags setzen (überschreibt existierende)
server.set_flags([msg_id], ['\\Seen', '\\Flagged'])

# Flags hinzufügen
server.add_flags([msg_id], ['\\Flagged'])

# Flags entfernen
server.remove_flags([msg_id], ['\\Seen'])

# Custom Flags/Labels (Gmail, etc.)
server.add_flags([msg_id], ['Important', 'NeedsReview'])

# Gmail Labels
server.add_gmail_labels([msg_id], ['Project/Urgent'])
server.remove_gmail_labels([msg_id], ['Project/Old'])
```

## 6. Nachrichten verschieben & kopieren

```python
# Nachricht in anderen Ordner verschieben
server.move([msg_id], 'Archive')

# Nachricht kopieren
server.copy([msg_id], 'Backup')

# Nachricht löschen (zwei Schritte)
server.add_flags([msg_id], ['\\Deleted'])
server.expunge()  # Endgültig löschen
```

## 7. Wichtige weitere IMAP-Features

### e) Weitere wichtige Funktionen

```python
# IDLE - Auf neue Nachrichten warten
server.idle()
# Warte auf Benachrichtigungen...
responses = server.idle_check(timeout=30)
server.idle_done()

# Thread-Informationen abrufen
threads = server.thread()

# Quota abfragen (falls unterstützt)
quota = server.get_quota()

# Server-Capabilities prüfen
capabilities = server.capabilities()
# z.B.: {b'IMAP4REV1', b'IDLE', b'NAMESPACE', b'QUOTA', ...}

# APPEND - Neue Nachricht in Ordner einfügen
msg = "From: sender@example.com\r\n..."
server.append('INBOX', msg, flags=['\\Seen'], msg_time=datetime.now())
```

## 8. Praktisches Beispiel für dein Klassifizierungs-System

```python
from imapclient import IMAPClient
from datetime import datetime

def analyze_mailbox():
    with IMAPClient('imap.gmail.com', ssl=True) as server:
        server.login('user@gmail.com', 'password')
        
        # Alle Ordner mit Statistiken
        print("\n=== Ordner-Übersicht ===")
        for flags, delimiter, folder_name in server.list_folders():
            try:
                status = server.folder_status(folder_name, ['MESSAGES', 'UNSEEN'])
                print(f"{folder_name}:")
                print(f"  Total: {status[b'MESSAGES']}")
                print(f"  Ungelesen: {status[b'UNSEEN']}")
            except:
                print(f"{folder_name}: Nicht zugänglich")
        
        # Inbox analysieren
        server.select_folder('INBOX')
        
        # Ungelesene Nachrichten
        unseen_ids = server.search(['UNSEEN'])
        print(f"\n{len(unseen_ids)} ungelesene Nachrichten")
        
        if unseen_ids:
            # Details abrufen
            fetch_data = server.fetch(unseen_ids[:10], ['FLAGS', 'ENVELOPE', 'RFC822.SIZE'])
            
            for msg_id, data in fetch_data.items():
                envelope = data[b'ENVELOPE']
                flags = data[b'FLAGS']
                size = data[b'RFC822.SIZE']
                
                print(f"\nMessage {msg_id}:")
                print(f"  Von: {envelope.from_[0].mailbox}@{envelope.from_[0].host}")
                print(f"  Betreff: {envelope.subject}")
                print(f"  Größe: {size} bytes")
                print(f"  Flags: {flags}")
                
                # Beispiel: Als gelesen markieren
                # server.add_flags([msg_id], ['\\Seen'])
                
                # Beispiel: Custom Label hinzufügen
                # server.add_flags([msg_id], ['AutoClassified'])

if __name__ == '__main__':
    analyze_mailbox()
```

## 9. Wichtige Hinweise

### Encoding
- Ordnernamen werden automatisch von Modified UTF-7 nach Unicode dekodiert
- Bei `folder_decode=False` bekommst du Raw-Bytes

### Performance
- `folder_status()` ist effizienter als `select_folder()` wenn du nur Stats brauchst
- Batch-Operationen mit Listen von UIDs sind schneller als Einzelaufrufe
- IDLE ist effizienter als Polling für Echtzeit-Updates

### Fehlerbehandlung
```python
from imapclient.exceptions import IMAPClientError

try:
    server.select_folder('DoesNotExist')
except IMAPClientError as e:
    print(f"Fehler: {e}")
```

### Gmail-Spezifika
- Gmail verwendet Labels statt Ordner
- `[Gmail]/All Mail` enthält alle Nachrichten
- X-GM-MSGID und X-GM-THRID sind verfügbar
- `gmail_search()` nutzt die Gmail-Suchsyntax

## 10. Nützliche Such-Kriterien

```python
# Datum-basierte Suche
server.search(['SINCE', '01-Jan-2024'])
server.search(['BEFORE', '31-Dec-2023'])

# Absender/Empfänger
server.search(['FROM', 'mike@example.com'])
server.search(['TO', 'info@company.com'])

# Betreff
server.search(['SUBJECT', 'Rechnung'])

# Status-kombinationen
server.search(['UNSEEN', 'UNFLAGGED'])

# Größe
server.search(['LARGER', 1000000])  # > 1MB
server.search(['SMALLER', 10000])   # < 10KB

# Kombinationen mit OR
server.search(['OR', 'FROM', 'alice@example.com', 'FROM', 'bob@example.com'])
```

## Ressourcen

- IMAPClient Docs: https://imapclient.readthedocs.io/
- IMAP RFC 9051: https://www.rfc-editor.org/rfc/rfc9051
- Email-Parsing: `email` Modul (Python Standard Library)
