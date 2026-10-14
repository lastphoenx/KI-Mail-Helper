# Microsoft 365 / Exchange Online — OAuth im Mail Helper

Persönliches Postfach über **IMAP + SMTP mit OAuth2 (XOAUTH2)** — analog zur Google-OAuth-Kachel, mit **eigener Entra-App pro Nutzer** (Client-ID + Secret im Setup).

Shared Mailboxes sind in dieser Version **nicht** enthalten.

## Ablauf: Wie du an das Token kommst

Du tippst **kein** Token manuell ein. Der Mail Helper holt es per **OAuth 2.0 Authorization Code**:

1. **Einstellungen** → Mail-Account hinzufügen → **Microsoft 365 OAuth**
2. **Client-ID** und **Client-Secret** deiner Entra-App eingeben (2FA-Schritt wie bei Google)
3. **Mit Microsoft anmelden** — Browser öffnet `login.microsoftonline.com`
4. Nach Login leitet Microsoft zurück auf  
   `…/settings/mail-account/microsoft/callback?code=…&state=…`
5. Der Server tauscht `code` gegen **Access Token** + **Refresh Token** (geheim, verschlüsselt in der DB)
6. IMAP/SMTP nutzen das Access Token per **XOAUTH2**; vor Ablauf wird per Refresh Token erneuert

## Entra-App registrieren (Kurz)

| Schritt | Inhalt |
|--------|--------|
| Portal | [App-Registrierungen](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade) |
| Redirect URI (Web) | Exakt die URL aus dem Setup-Screen (`/settings/mail-account/microsoft/callback`) |
| Geheimnis | Client secret erstellen und **einmal** im Mail Helper eingeben |
| Delegierte Rechte | **Office 365 Exchange Online:** `IMAP.AccessAsUser.All`, `SMTP.Send` — **Microsoft Graph:** `User.Read`, `offline_access` |

Uni-Tenant: ggf. **Administratorzustimmung** für die App — sonst schlägt der Login mit «consent»/Berechtigung fehl.

## Server-Einstellungen (automatisch)

| Protokoll | Host | Port | Auth |
|-----------|------|------|------|
| IMAP | `outlook.office365.com` | 993 | SSL + XOAUTH2 |
| SMTP | `smtp.office365.com` | 587 | STARTTLS + XOAUTH2 |

Campus-SMTP per VPN (z. B. `smtp.university.example`, Port 25) ist **nicht** dieser OAuth-Weg.

## Funktionen

- Mail-Abruf (Celery) über IMAP wie klassische Konten
- **Ordner-Audit** für Microsoft-OAuth-Konten
- Ausgehende Mail über `SMTPSender` mit demselben Token

## Fehlerbilder

| Symptom | Typische Ursache |
|---------|------------------|
| Kein Refresh Token | Beim ersten Consent `prompt=consent`; Secret/Redirect falsch |
| `invalid_client` | Client-ID/Secret falsch oder Secret abgelaufen |
| IMAP AUTH failed | Fehlende API-Berechtigung `IMAP.AccessAsUser.All` oder Basic Auth Policy (selten) |
| Admin approval required | Uni-IT muss App im Tenant freigeben |

## Technik (Entwickler)

- Modul: `src/11_microsoft_oauth.py`
- IMAP: `MailFetcher.for_oauth2()` → `imapclient.oauth2_login`
- Factory: `src/helpers/imap_fetcher_factory.py`
- App-Credentials (Client-ID/Secret): verschlüsselt in SMTP-Username/Password-Feldern (`oauth_app_credentials.py`)
