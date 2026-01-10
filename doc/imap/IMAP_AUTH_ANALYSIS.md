# Technische Analyse: IMAP Authentifizierungsfehler

## Fehler im Log

```
❌ Fehler beim Zählen: Error: Fehler beim Zählen: IMAP connection failed
✅ Verbunden mit imap.gmx.net
❌ Verbindungsfehler: Authentifizierung fehlgeschlagen
```

## Code-Analyse

### Problemstelle 1: MailFetcher.connect() 
**Datei**: [src/06_mail_fetcher.py](src/06_mail_fetcher.py#L246-L257)

```python
def connect(self):
    """Stellt Verbindung zum IMAP-Server her (IMAPClient)"""
    try:
        self.connection = IMAPClient(
            host=self.server,
            port=self.port,
            ssl=True,
            timeout=30.0
        )
        self.connection.login(self.username, self.password)  # ← HIER PASSIERT FEHLER
        print(f"✅ Verbunden mit {self.server}")
    except (IMAPClientError, Exception) as e:
        logger.debug(f"Connection error details: {e}")
        print("❌ Verbindungsfehler: Authentifizierung fehlgeschlagen")
        raise ConnectionError("IMAP connection failed") from None
```

**Problem**: 
- Zeile 246: `IMAPClient(host=..., port=..., ssl=True)` → Verbindung erfolgreich ✅
- Zeile 249: `self.connection.login(self.username, self.password)` → **FEHLER** ❌
- Grund: `username` oder `password` sind falsch!

### Problemstelle 2: get_account_mail_count()
**Datei**: [src/01_web_app.py](src/01_web_app.py#L5820-L5890)

```python
def get_account_mail_count(account_id):
    # ... Credentials aus DB entschlüsseln ...
    fetcher = mail_fetcher_mod.MailFetcher(
        server=imap_server,
        username=imap_username,
        password=imap_password,
        port=account.imap_port,
    )
    fetcher.connect()  # ← Exception wird hier geworfen
```

## Wo kommen die Credentials her?

### 1. Eingabe: [src/01_web_app.py](src/01_web_app.py#L4930-L5030)
```python
@app.route("/settings/mail-account/add", methods=["GET", "POST"])
def add_mail_account():
    # Form-Input
    imap_username = request.form.get("imap_username")  # Benutzer gibt ein
    imap_password = request.form.get("imap_password")  # Benutzer gibt ein
    
    # Verschlüsselung
    encrypted_password = encryption.CredentialManager.encrypt_imap_password(
        imap_password, master_key
    )
```

### 2. Abruf: [src/01_web_app.py](src/01_web_app.py#L5866-L5874)
```python
imap_server = encryption.CredentialManager.decrypt_server(
    account.encrypted_imap_server, master_key
)
imap_username = encryption.CredentialManager.decrypt_email_address(
    account.encrypted_imap_username, master_key
)
imap_password = encryption.CredentialManager.decrypt_imap_password(
    account.encrypted_imap_password, master_key
)
```

## Diagnose-Checkliste

### ❓ Was war bei der Registrierung eingegeben?

1. **Benutzername**: War es `thomas@gmx.net` oder nur `thomas`?
   - ✅ Korrekt: `thomas@gmx.net` (vollständig)
   - ❌ Falsch: `thomas` (nur lokal)

2. **Passwort**: War es das normale GMX-Passwort oder ein App-Passwort?
   - GMX mit 2FA: Benötigt **App-Passwort** (16-stellig)
   - GMX ohne 2FA: Normales Passwort OK

3. **Port**: 993 ist korrekt für imap.gmx.net

4. **Server**: imap.gmx.net ist korrekt

## Lösung

### Variante A: App-Passwort erstellen (empfohlen)
1. https://www.gmx.net → Sicherheit
2. "App-Passwort generieren"
3. 16-stelliges Passwort kopieren (OHNE Bindestriche!)
4. In der App neu eingeben

### Variante B: Account neu hinzufügen
1. Alten Account löschen (Schaltfläche in Settings)
2. Neu hinzufügen mit korrektem Passwort
3. Testen mit "Mail-Count" API

### Variante C: Debugging aktivieren
Um zu sehen, WAS genau falsch ist:

```python
# In 06_mail_fetcher.py, Zeile 255, ändern:
except (IMAPClientError, Exception) as e:
    print(f"❌ Verbindungsfehler: {e}")  # ← Zeige echten Fehler
    logger.error(f"Full error: {type(e).__name__}: {e}")
    raise ConnectionError("IMAP connection failed") from None
```

Dann schaue in den Logs, was der echte Fehler ist:
- `Authentication failed` → Passwort falsch
- `STARTTLS required` → Port/SSL-Einstellung falsch
- `SSL: certificate verify failed` → Zertifikatsproblem
- `Connection timed out` → Server nicht erreichbar

## Code-Verbesserungen

1. **Bessere Fehlermeldungen** in MailFetcher.connect()
   - Momentan: Generischer "IMAP connection failed"
   - Sollte: Spezifischer "Authentication failed: invalid credentials"

2. **Validierung vor Speichern** in add_mail_account()
   - Momentan: Credentials nur auf Form-Validierung
   - Sollte: Test-Verbindung machen vor Speichern

3. **Automatische Passwort-Normalisierung**
   - Bindestriche aus App-Passwörtern entfernen
   - Leerzeichen trimmen
