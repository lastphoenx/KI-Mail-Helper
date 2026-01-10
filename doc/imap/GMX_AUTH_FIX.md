# GMX IMAP Authentifizierung - Troubleshooting Guide

## Problem
```
✅ Verbunden mit imap.gmx.net
❌ Verbindungsfehler: Authentifizierung fehlgeschlagen
```

## Ursache
**GMX mit 2-Faktor-Authentifizierung (2FA) aktiviert?**
→ Normales Passwort funktioniert NICHT!

## Lösung Schritt-für-Schritt

### 1. GMX App-Passwort erstellen
1. Gehe zu **https://www.gmx.net** → anmelden
2. **Sicherheit** → **Passwörter** 
3. **App-Passwort generieren** (für "Anderer Client")
4. Du erhältst eine 16-stellige Nummer: `XXXX-XXXX-XXXX-XXXX`

### 2. In der App verwenden
- **IMAP Server**: `imap.gmx.net`
- **Port**: `993` (SSL)
- **Benutzername**: Deine vollständige E-Mail-Adresse (z.B. `thomas@gmx.net`)
- **Passwort**: Das 16-stellige App-Passwort (OHNE Bindestriche!)
  - Beispiel: `ABCDEFGHIJKLMNop` (16 Zeichen)

### 3. Alternative: Ohne 2FA
Falls du 2FA ausschalten möchtest (nicht empfohlen):
1. GMX Settings → Sicherheit → 2FA deaktivieren
2. Dann funktioniert dein normales Passwort

## SMTP (falls auch nötig)
- **SMTP Server**: `mail.gmx.net`
- **Port**: `587` (STARTTLS) ODER `465` (SSL)
- **Benutzername**: Deine E-Mail-Adresse
- **Passwort**: Das App-Passwort (nicht dein normales Passwort!)

## Häufige Fehler
- ❌ App-Passwort mit Bindestrichen eingeben (`XXXX-XXXX-...`)
  → ✅ Bindestriche entfernen!
- ❌ Falscher Benutzername (nur `thomas` statt `thomas@gmx.net`)
  → ✅ Komplette E-Mail-Adresse verwenden
- ❌ Normales Passwort bei 2FA aktiviert
  → ✅ App-Passwort generieren

## Test in der App
1. **Account hinzufügen** → IMAP
2. Gib alle Werte ein (E-Mail, App-Passwort, etc.)
3. Nach dem Speichern sollte es funktionieren!

Wenn es IMMER NOCH nicht funktioniert, dann ist wahrscheinlich:
- Benutzername falsch eingegeben
- IMAP in GMX-Einstellungen nicht aktiviert
- Firewall/Proxy blockiert Port 993
