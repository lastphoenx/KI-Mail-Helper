# IMAP Documentation

Diese Dokumentation wurde während Phase 11.5 erstellt und hilft bei der korrekten IMAPClient-Implementierung.

## Verfügbare Dokumente:

1. **DIAGNOSE_PHASE11_2025-12-29.md** - Vollständige Analyse des gescheiterten Versuchs
   - Identifizierte Bugs (bytes-to-JSON, RFC822 vs BODY.PEEK[])
   - Git-Historie Analyse
   - Empfehlung für Clean Rebuild

2. **imap_complete_handbook.md** & **imap_api_reference.md** - VERLOREN
   - Waren nicht im Git committed
   - Können bei Bedarf aus IMAPClient Docs neu erstellt werden
   - Siehe: https://imapclient.readthedocs.io/

## Lessons Learned:

✅ **Was funktioniert hat:**
- MailFetcher Connection Management
- IMAP Login/Logout
- Folder-Liste abrufen (mit korrektem bytes-Handling)

❌ **Was NICHT funktioniert hat:**
- RFC822 im readonly-Modus
- bytes-to-JSON Konvertierung
- Fehlende Exception-Details
- Ungetesteter Code (70KB ohne Tests)

## Nächste Schritte:

Phase 11 Rebuild mit:
- Test-First Development
- Kleine, testbare Commits
- IMAPClient Docs lesen BEVOR implementieren
- Jeden API-Call mit Logs versehen
