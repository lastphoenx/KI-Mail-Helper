# 🔒 Security-Audit & Produktivitäts-Roadmap — September 2026

**Kontext:** Vollständige Code-Prüfung (White-Box-Pentest/Security-Review) vor Live-Gang, plus Vorschläge zur produktiven Weiterentwicklung (Nextcloud/OpenProject/XWiki-Integration).

**Methode:** Kein Black-Box-Pentest gegen eine laufende Instanz (keine deployte Instanz verfügbar), sondern eine **vollständige White-Box-Code-Prüfung** von vier spezialisierten Reviews parallel:
1. Auth/Session/Crypto (Login, 2FA, DEK/KEK-Verschlüsselung, OAuth)
2. API/Blueprints (IDOR, SQL-Injection, SSRF, Autorisierung)
3. Infrastruktur/Config/Dependencies (Headers, systemd, Gunicorn, CVEs)
4. Mail-/AI-Pipeline (IMAP/SMTP, Cloud-KI-Anbindung, Anonymisierung, Auto-Rules)

Jeder Fund wurde gegen den tatsächlichen Code verifiziert (Datei:Zeile), nicht nur gegen die Dokumentation in `docs/SECURITY.md`. Das Ergebnis vorweg: **die Architektur ist grundsätzlich solide** (Zero-Knowledge-Verschlüsselung korrekt implementiert, keine SQL-Injection, keine XSS-Lücken, IDOR-Checks fast überall vorhanden, TLS-Verifikation aktiv, CSRF global aktiv). Die gefundenen Lücken sind reale, aber gezielt behebbare Einzelprobleme — kein grundlegendes Architekturproblem.

**Von den unten gelisteten Findings wurden 17 in dieser Session direkt im Code behoben** (siehe ✅-Markierung), die verbleibenden sind bewusst nicht blind gefixt, weil sie entweder eine Produktentscheidung erfordern (z. B. Admin-Rollensystem) oder ohne laufende Testumgebung (Postgres/Redis/volle ML-Dependencies waren in dieser Session nicht verfügbar) zu riskant zum "blind" ändern waren. Für alle offenen Punkte steht eine konkrete Umsetzungsempfehlung dabei.

---

## Teil A: Security-Findings

### 🔴 Kritisch

#### A1. ✅ FIXED — Fail-Open PII-Leak an Cloud-LLM bei Anonymisierungsfehler
**Dateien:** `src/tasks/email_processing_tasks.py` (reprocess_email_base, optimize_email_processing)

Die beiden Celery-Tasks für "Basis-Lauf" und "Optimize-Lauf" riefen `get_or_create_sanitized_content()` **ohne** `require_anonymization=use_cloud` auf. Schlug die Anonymisierung fehl (spaCy-Crash, DB-Fehler beim Speichern der sanitisierten Version etc.), gab die Funktion still den **unsanitisierten Originaltext** zurück (`was_anonymized=False`) — und beide Tasks schickten diesen Text trotzdem ungeprüft an OpenAI/Anthropic/Mistral. Zusätzlich wurde der **Betreff nie sanitisiert** (nur der Body), selbst wenn Cloud-Anonymisierung lief.

Damit konnten bei jedem transienten Fehler Klarnamen, Adressen, IBANs etc. an einen Cloud-Anbieter gehen — genau das, was die Zero-Knowledge/DSGVO-Architektur verhindern soll. Der bereits korrekt implementierte Task `reply_generation_tasks.py` diente als Vorlage für den Fix.

**Fix:** `require_anonymization=use_cloud` ergänzt, `SanitizationError`/`was_anonymized`-Check führt jetzt zu `Reject` (Task bricht ab) statt zu stillem Klartext-Versand; Betreff wird jetzt ebenfalls aus dem sanitisierten Ergebnis genommen.

---

### 🟠 Hoch

#### A2. ✅ FIXED — IBANs wurden nie vor Cloud-Versand redigiert
**Datei:** `src/services/content_sanitizer.py`

Der aktive Sanitizer (`ContentSanitizer._apply_regex`) hatte Regex für E-Mail, Telefon, URL, HRB/UST-ID — aber **keine IBAN-Erkennung** (der alte, nicht mehr genutzte `04_sanitizer.py` hatte sie, ging beim Rewrite verloren). Jede Rechnungs-/Zahlungs-Mail hätte die volle Bankverbindung an Cloud-Anbieter geschickt, selbst bei erfolgreicher Anonymisierung.

**Fix:** IBAN-Regex ergänzt (vor der Telefon-Erkennung, da IBANs sonst fälschlich als Telefonnummer erkannt werden), inkl. Längenvalidierung (15–34 Zeichen normalisiert).

#### A3. ✅ FIXED — Timing-Seitenkanal hebelt Login-Enumeration-Schutz aus
**Datei:** `src/blueprints/auth.py`

Der "Dummy-Hash-Check" bei unbekanntem Username nutzte ein **bcrypt-Format** (`$2b$12$...`), die App aber **Werkzeugs** `check_password_hash` (scrypt-Format). Werkzeug erkennt bcrypt-Hashes nicht, wirft sofort `ValueError` (~36µs) statt die ~86ms eines echten scrypt-Checks zu brauchen — ein Faktor-2400-Timing-Unterschied, über das Netz messbar. Ein Angreifer kann damit zuverlässig gültige Usernamen enumerieren, obwohl der Code das explizit verhindern sollte.

**Fix:** Dummy-Hash wird jetzt einmalig beim Modul-Import per echtem `generate_password_hash()` erzeugt (gleiches Format/gleiche Kosten wie echte Passwort-Hashes).

#### A4. ✅ FIXED — SSRF über frei konfigurierbaren IMAP/SMTP-Host
**Neue Datei:** `src/helpers/network_safety.py` · **Betroffen:** `src/06_mail_fetcher.py`, `src/19_smtp_sender.py`, `src/imap_diagnostics.py`, `src/blueprints/accounts.py`, `src/services/imap_sender_scanner.py`

Jeder eingeloggte User kann beim Anlegen eines "Mail-Accounts" einen beliebigen Host+Port eintragen. Weder beim Speichern noch beim Verbindungsaufbau wurde geprüft, ob dieser Host auf `127.0.0.1`, private Netze (RFC1918) oder Cloud-Metadata-Adressen (`169.254.169.254`) zeigt. Über Diagnose-Endpoints (`/api/imap-diagnostics/<id>`) oder den Fetch-Vorgang konnte der Server so als **SSRF-Werkzeug für internes Port-Scanning/Banner-Grabbing** missbraucht werden.

**Fix:** Neues Modul `assert_safe_mail_host()` (IP-Auflösung + Block von privaten/loopback/link-local/reserved Adressen), eingebunden an **allen sechs** Stellen, wo tatsächlich ein Socket zu einem User-konfigurierten Host geöffnet wird — bei **jedem** Verbindungsversuch neu geprüft (nicht nur beim Speichern), damit DNS-Rebinding nichts bringt. Für bewusstes Self-Hosting im eigenen Netz per `ALLOW_PRIVATE_MAIL_HOSTS=true` deaktivierbar.

#### A5. ✅ FIXED — fail2ban überwacht die falsche Log-Datei (wirkungslos im Standard-Setup)
**Dateien:** `src/app_factory.py`, `config/fail2ban-jail.conf`

`SECURITY[LOGIN_FAILED]`/`SECURITY[LOCKOUT]`-Zeilen wurden nur geloggt, wenn `src/00_main.py` importiert wird (dort steht das einzige `logging.basicConfig(...)` im ganzen Code). Produktiv startet systemd aber Gunicorn **direkt** gegen `src.app_factory:create_app()` — `00_main.py` läuft nie. Ohne konfigurierten Handler landen die Zeilen nur über Pythons "Handler of last resort" auf stderr, was je nach systemd-Setup in `logs/systemd_error.log` landet — **nicht** in der von `fail2ban-jail.conf` beobachteten `/var/log/mail-helper/gunicorn_error.log`. Ergebnis: **fail2ban bannt nie jemanden**, obwohl es aktiv konfiguriert aussieht.

**Fix:** `app_factory.py` konfiguriert jetzt beim Modul-Import explizit einen `FileHandler` auf `logs/security.log` (Pfad relativ zum App-Verzeichnis, unabhängig vom Entry-Point). `fail2ban-jail.conf` zeigt jetzt auf diesen tatsächlichen Pfad.

#### A6. ✅ FIXED — Rate-Limiter läuft standardmäßig In-Memory unter Multi-Worker-Gunicorn
**Dateien:** `src/app_factory.py`, `.env.example`

`RATE_LIMIT_STORAGE` defaultete auf `memory://`. Unter Gunicorn mit mehreren Worker-Prozessen (`config/gunicorn.conf.py`: `2×CPU+1`) hat **jeder Worker seinen eigenen Zähler** — aus "5 Login-Versuche/Minute" werden effektiv "5 × Worker-Anzahl". `.env.example` setzte `RATE_LIMIT_STORAGE` nirgends, sodass ein Admin, der die Vorlage übernimmt, unbemerkt mit geschwächtem Brute-Force-Schutz läuft, obwohl Redis für Celery ohnehin Pflicht ist.

**Fix:** Default ist jetzt `auto` — erkennt Redis automatisch (nutzt Host/Port aus `REDIS_URL`, eigene DB 3) und fällt nur bei nicht erreichbarem Redis auf `memory://` zurück, dann mit lauter Warnung (ERROR-Level in Produktion). `.env.example` dokumentiert die Option.

---

### 🟡 Mittel

#### A7. ✅ FIXED — Rate-Limiter in `thread_api.py` war nie an die App gebunden (toter Code)
**Datei:** `src/thread_api.py`

Ein **eigener, lokaler** `Limiter(...)` wurde erzeugt, aber nie per `init_app(app)` gebunden — die `@limiter.limit(...)`-Decorators auf `/api/threads*` griffen dadurch nie. `/api/threads/search` lädt zudem bei jeder Anfrage **alle** E-Mails des Users zur Entschlüsselung (keine serverseitige Suche auf verschlüsselten Feldern möglich) — ein potenziell teurer, faktisch unlimitierter Endpoint.

**Fix:** Nutzt jetzt den echten, app-gebundenen Limiter aus `app_factory.py` (gleiches Muster wie bereits korrekt in `accounts.py` verwendet).

#### A8. ✅ FIXED — ReDoS über User-definierte Regex in Auto-Rules
**Datei:** `src/auto_rules_engine.py`

`subject_regex`/`body_regex` in Auto-Rules kommen vollständig vom User (`POST /api/rules`) und laufen bei **jeder** eingehenden E-Mail auf einem geteilten Celery-Worker. Ein Pattern mit katastrophalem Backtracking (`(a+)+$`) hätte den Worker-Prozess für **alle** User blockiert — ohne jeden Timeout.

**Fix + Verifikation:** Timeout-geschützte Regex-Auswertung ergänzt. Wichtig: Ein naiver Thread+`join(timeout=...)`-Ansatz (wie ihn `04_sanitizer.py` als Fallback nutzt) **funktioniert bei rein CPU-gebundenem Backtracking nicht**, weil CPython die GIL während `re.search()` nicht freigibt — das wurde hier empirisch nachgewiesen (Timeout ignoriert, 75s statt 1s). Der neue Fix nutzt stattdessen `signal.SIGALRM` im Hauptthread (funktioniert nachweislich — CPython prüft während Regex-Matching auf anstehende Signale) und ist damit für die tatsächliche Deployment-Topologie (Celery `--pool=prefork`, Gunicorn `worker_class=sync` — beide Hauptthread-pro-Prozess) wirksam getestet. Threading-Fallback bleibt für Nicht-Hauptthread-Kontexte (z. B. Tests) als Best-Effort erhalten.

#### A9. ✅ FIXED (teilweise) — Kostenintensive Endpoints ohne Rate-Limit
**Dateien:** `src/blueprints/translator.py`, `src/blueprints/training.py`

`/api/translate/detect` und `/api/translate/execute` riefen ungebremst Cloud-LLM-APIs mit den **eigenen** Provider-Keys der App auf — jeder eingeloggte User konnte damit Kosten hochtreiben. `/retrain` triggerte ein potenziell schweres, komplett unlimitiertes globales Retraining.

**Fix:** Rate-Limits ergänzt (30/min Detect, 20/min Execute, 3/h Retrain).

**Nicht angefasst (bewusst):** `train_from_corrections()` trainiert laut Code einen **globalen** Klassifikator aus den Korrekturen **aller** User kombiniert — das könnte ein bewusstes Architektur-Detail sein (README erwähnt separat einen "Personal Classifier" pro User als Ergänzung zum globalen Modell mit Fallback-Kette Personal→Global→AI-Only). Das wurde **nicht** verändert, da unklar ist, ob geteiltes globales Lernen gewünscht ist — das solltet ihr bewusst entscheiden/dokumentieren, nicht ich blind "fixen".

#### A10. ✅ FIXED — Account-Lockout schützte nur die Passwort-Eingabe, nicht 2FA
**Datei:** `src/blueprints/auth.py`

`is_locked()`/`record_failed_login()` wurden nur beim Passwort-Check aufgerufen. `/2fa/verify` hatte **keinen** Account-seitigen Schutz — nur das per-IP-Rate-Limit (5/min), das über Proxies/Botnetze trivial umgangen werden kann. Wer ein geleaktes Passwort hat, konnte TOTP-Codes/Recovery-Codes ungebremst gegen genau diesen einen Account raten.

**Fix:** Gleicher Lockout-Zähler wird jetzt auch bei fehlgeschlagener 2FA-Verifikation genutzt (record bei Fehlschlag, reset bei Erfolg, Lockout-Check vor der Verifikation) — ohne Schema-Änderung, da derselbe Zähler wiederverwendet wird.

#### A11. ✅ FIXED — Klartext-DEKs in `service_tokens` wurden nie automatisch aufgeräumt
**Neue Datei:** `src/tasks/maintenance_tasks.py` · **Geändert:** `src/celery_app.py`

`ServiceToken.encrypted_dek` speichert (dokumentiert, bewusst) den **Klartext-DEK** eines Users, damit Celery-Tasks ohne aktive Flask-Session auf Mails zugreifen können. Schutz: nur die TTL (Standard: mehrere Tage). Es gab aber **keinen periodischen Reaper** — abgelaufene Zeilen wurden nur beim expliziten `/logout` gelöscht. Schließt ein User (der häufigere Fall) nur den Tab, blieb der Klartext-DEK bis zu Tage in der DB stehen. Ein DB-Dump in diesem Fenster hebelt Zero-Knowledge für den betroffenen User komplett aus — ganz ohne dessen Passwort.

**Fix:** Neuer stündlicher Celery-Beat-Task `cleanup_expired_service_tokens`, der abgelaufene Zeilen löscht. **Wichtig:** greift nur, wenn `celery beat` tatsächlich läuft (`config/mail-helper-celery-beat.service`) — bitte beim Deployment sicherstellen.

---

### 🟢 Niedrig (alle behoben)

#### A12. ✅ FIXED — Cross-Tenant-Leak: Korrektur-Zähler ohne User-Filter
**Datei:** `src/blueprints/email_actions.py` — `correction_count` in `correct_email()` zählte über **alle** User hinweg statt nur den eigenen. Fix: Join über `RawEmail.user_id`.

#### A13. ✅ FIXED — Anhang-Dateiname ungefiltert in Content-Disposition
**Datei:** `src/blueprints/emails.py` — Absenderkontrollierter `attachment.filename` ging ungefiltert in `send_file(download_name=...)`. Moderne Werkzeug-Versionen quoten das zwar sicher, aber als Defense-in-Depth jetzt Pfadanteile/Steuerzeichen (inkl. CR/LF) entfernt — ohne (wie `werkzeug.secure_filename()`) internationale Zeichen wie Umlaute zu zerstören.

#### A14. ✅ FIXED — DB-Credentials im Klartext auf stdout beim Migrations-Skript
**Datei:** `scripts/migrate_sqlite_to_postgresql.py` — `--target postgresql://user:pass@host/db` wurde 1:1 auf stdout geprintet (landet in Logs/Terminal-Historie). Fix: Passwort wird vor der Ausgabe maskiert.

#### A15. ✅ FIXED — Vorhersehbarer Temp-Datei-Pfad im Backup-Skript
**Datei:** `scripts/backup_database.sh` — `/tmp/backup_test_$$.db` (PID-basiert, vorhersehbar/wiederverwendbar) durch `mktemp` + `chmod 600` ersetzt.

#### A16. ✅ FIXED — Kein `Cache-Control: no-store` auf Recovery-Code-Seiten
**Datei:** `src/blueprints/auth.py` — Seiten mit einmaligen Recovery-Codes (`setup_2fa_success.html`, `recovery_codes_regenerated.html`) konnten vom Browser gecacht und nach Logout über Zurück-Button/Verlauf erneut aufgerufen werden.

#### A17. ✅ FIXED — Inkonsistente/veraltete Pfade in systemd-Unit-Dateien
**Dateien:** `config/mail-helper-celery-worker.service`, `-celery-beat.service`, `-celery-flower.service`, `-processor.service` — nutzten `/home/mailhelper/projects/KI-Mail-Helper-Dev` + `.env.local`, während die Haupt-App (`mail-helper.service`) `/opt/KI-Mail-Helper` + `.env` nutzt. Bei unveränderter Installation liefen Celery-Worker/Beat mit anderem `SECRET_KEY`/`DATABASE_URL`/Redis als die Web-App. Alle vier Dateien jetzt auf die gleiche Konvention vereinheitlicht.

---

### 📋 Offen — bewusst nicht blind gefixt (Empfehlung + Begründung)

| # | Finding | Datei(en) | Warum nicht auto-gefixt | Empfehlung |
|---|---|---|---|---|
| B1 | **Session-Fixation:** Session-ID wird bei Login/2FA-Erfolg nie rotiert | `src/blueprints/auth.py` | Kernstück der Auth-Logik; ohne laufende Postgres/Redis/Flask-Umgebung in dieser Session nicht end-to-end testbar — ein Fehler hier wäre schlimmer als der Status quo | Nach `login_user()` und nach `/2fa/verify`-Erfolg Flask-Session-Datei rotieren lassen (neue `sid` erzwingen), dann mit echtem Login-Flow testen |
| B2 | **TOTP-Replay:** Gültiger 6-stelliger Code kann innerhalb seines Zeitfensters (~60–90s) mehrfach verwendet werden | `src/07_auth.py` | Erfordert Schema-Migration (neue Spalte `last_totp_step`) | Migration + Check "Step ≤ letzter akzeptierter Step" ergänzen (analog `migrations/`-Konvention) |
| B3 | Passwortänderung invalidiert keine anderen aktiven Sessions/ServiceTokens | `src/blueprints/accounts.py` | Erfordert Session-Enumeration-Mechanismus (Flask-Session Filesystem-Backend bietet das nicht out-of-the-box) | Bei Passwortänderung zusätzlich alle `ServiceToken`-Rows des Users löschen (kleiner Fix, analog `/logout`); Session-weite Invalidierung als größeres Vorhaben planen |
| B4 | Recovery-Code-Verifikation hat theoretisches TOCTOU-Race (Code doppelt nutzbar) | `src/07_auth.py` | Braucht atomares `UPDATE ... WHERE used_at IS NULL RETURNING`-Pattern, ähnlich dem bereits korrekt genutzten Lockout-Counter — kontrollierte Änderung, aber Zeitbudget | Selbes Muster wie Lockout-Counter in `02_models.py` übernehmen |
| B5 | Kein echtes Admin-Rollensystem (`admin.py` hat nur `@login_required`, keine Rolle) | `src/blueprints/admin.py` | Architekturentscheidung (welche Rollen? wer wird Admin?) — eure Entscheidung, nicht meine | `is_admin`-Spalte + `@admin_required`-Decorator einführen, **bevor** weitere Admin-Routen ergänzt werden |
| B6 | ML-Classifier-Pickle-Integritätsprüfung (HMAC) ist optional, nicht Pflicht | `src/03_ai_client.py` | Verpflichtend machen würde alle bestehenden Installationen ohne vorbereitete `.sig`-Dateien sofort auf Heuristik-Fallback zurückwerfen — es gibt noch kein Tooling, das diese Signaturen erzeugt | Signierungs-Skript für `.pkl`-Dateien bauen, dann `CLASSIFIER_HMAC_KEY` verpflichtend machen |
| B7 | `flask-talisman` ist deklarierte Dependency, aber nirgends aktiv genutzt (toter Code) | `src/app_factory.py`, `requirements.txt` | Kein Sicherheitsproblem selbst (die manuellen Header sind bereits gut: CSP mit Nonce, kein `unsafe-inline` im script-src, HSTS, X-Frame-Options DENY) — nur potenziell irreführend | Entweder Dependency entfernen oder bewusst integrieren; nicht dringend |
| B8 | `EnvironmentFile`-Berechtigungen (`.env`) werden nirgends erzwungen | `config/*.service` | Reine Doku-/Ops-Maßnahme | Deployment-Checkliste/Install-Skript um `chmod 600 .env* && chown mailhelper:mailhelper .env*` ergänzen |
| B9 | Legacy-Migrationspfad für alte Master-Keys nutzt schwächere KDF (100k statt 600k PBKDF2-Iterationen) | `src/08_encryption.py` | Vermutlich nur für Alt-Accounts relevant, die noch nicht migriert sind | Prüfen, ob noch Accounts diesen Pfad nutzen; wenn nein, Code entfernen |
| B10 | Cloud-AI-SDKs veraltet (`anthropic==0.7.7`, `openai==1.3.7`, `mistralai==0.0.8`) | `requirements.txt` | Kein bekanntes CVE, aber sehr alte Versionen relativ zu aktuellen Releases | Dependency-Freshness-Pass einplanen (kein Blocker für Go-Live) |
| B11 | `nginx`-Config nicht im Repo — `ProxyFix(x_for=1)` vertraut dem ersten Hop | *(extern)* | Kann ohne die tatsächliche nginx-Config nicht verifiziert werden | Vor Go-Live sicherstellen: `proxy_set_header X-Forwarded-For $remote_addr;` (nicht `$proxy_add_x_forwarded_for` mit Client-Header-Durchreichung) — sonst kann das Rate-Limiting per gefälschtem `X-Forwarded-For` umgangen werden |

---

### ✅ Was bereits solide war (verifiziert, nicht nur behauptet)

- **Keine SQL-Injection:** einzige rohe `text()`-Query nutzt korrekt gebundene Parameter; sonst durchgehend SQLAlchemy ORM
- **IDOR:** praktisch jede `<int:id>`-Route filtert nach `user_id`/Ownership-Chain; die wenigen `.get(id)`-Aufrufe in `api.py` haben unmittelbar danach einen expliziten Ownership-Check
- **XSS:** Mail-HTML läuft in sandboxed iframe mit `script-src 'none'`, nicht `|safe` gerendert; Jinja2-Auto-Escaping sonst intakt
- **CSRF:** `CSRFProtect` global aktiv, alle Forms haben Token, keine `@csrf.exempt`
- **AES-GCM:** durchgehend frische `os.urandom(12)`-Nonces, keine Wiederverwendung
- **OAuth (Google):** `redirect_uri` immer serverseitig generiert, `state`-Parameter korrekt validiert
- **TLS:** IMAP/SMTP nutzen durchgehend Default-Verifikationskontext, kein `ssl.CERT_NONE`
- **SMTP-Header-Injection:** Pythons `email`-Paket verhindert CRLF-Injection in Headern zuverlässig
- **Passwort-Policy:** 24 Zeichen Minimum + Komplexität + HIBP-Check (k-Anonymität korrekt implementiert), konsistent an beiden Stellen (Register/Change) durchgesetzt
- **Rate-Limiting-Mechanik selbst:** trotz ungewöhnlicher Schreibweise (`limiter.limit(...)(view_func)`) funktional korrekt verifiziert
- **CORS:** nirgends `flask-cors` o. Ä. — API ist Same-Origin per Default
- **Keine bekannten CVEs** in den geprüften Kern-Dependencies (Flask 3.1.3, Werkzeug 3.1.6, cryptography 46.0.6, Jinja2 3.1.6, gunicorn 23.0.0, requests 2.32.5, PyYAML 6.0.3 — alle nach den relevanten CVE-Fixes released)

---

## Teil B: Vorschläge für produktiven Einsatz & Integrationen

Die App ist als E-Mail-Organizer mit KI-Priorisierung, Auto-Rules und Kalender-**Erkennung** (iCalendar REQUEST/REPLY/CANCEL) bereits stark. Was fehlt, um sie zur zentralen Schaltstelle für "aus E-Mail wird Aufgabe/Termin/Beleg" zu machen, ist die **Schreibrichtung** in andere Systeme — das ist aktuell komplett unbenutzt (verifiziert: keine Calendar-Write-Back-, Webhook- oder Nextcloud/OpenProject/XWiki-Anbindung im Code vorhanden; Auto-Rules können bisher nur verschieben/markieren/taggen, nicht extern etwas anlegen).

### B1. Nextcloud — naheliegendster erster Schritt

Ihr nutzt laut eurem Doku-Repo bereits Nextcloud im Homelab (`Raspi/nextcloud/`) — die Integration zahlt direkt auf vorhandene Infrastruktur ein.

- **Kalender (CalDAV):** Die App erkennt bereits iCalendar-Einladungen. Nächster Schritt: erkannte Termine per CalDAV-`PUT` (Standard-WebDAV, kein Nextcloud-spezifisches API nötig) direkt in den Nextcloud-Kalender des Users schreiben, statt nur eine Badge in der UI zu zeigen. Python: `caldav`-Library oder direkter `requests.put()` gegen `/remote.php/dav/calendars/{user}/{kalender}/`.
- **Tasks (VTODO via CalDAV):** Als KI-erkannt markierte "muss beantwortet werden bis Freitag"-Mails als Nextcloud-Task anlegen — gleiche CalDAV-Mechanik, nur `VTODO` statt `VEVENT`.
- **Nextcloud Tables (seit NC 27, hat REST-API):** Für strukturierte Daten aus E-Mails (z. B. erkannte Rechnungen/Belege) der pragmatischste Weg zu einer nutzbaren Tabellen-UI — deutlich weniger Aufwand als eine eigene Nextcloud-App, aber sofort brauchbar (Filter, Sortierung, CSV-Export für Buchhaltung).
- **Nextcloud Deck (Kanban, REST-API `/index.php/apps/deck/api/v1.0/`):** Alternative/Ergänzung zu Tables, wenn ihr einen Kanban-Workflow für "E-Mail → To-Do" wollt.
- **Auth:** Nextcloud **App-Passwörter** (in den Nextcloud-Einstellungen generierbar) — Speicherung analog zu den bestehenden IMAP/SMTP-Credentials (gleiches DEK/KEK-Verschlüsselungsmuster wiederverwenden, kein neues Sicherheitskonzept nötig).

**Zur explizit erwähnten Spesenerfassungs-Idee:** Die App erkennt über den Folder-Audit bereits Finanz-Keywords (CH/DE/IT/FR). Empfehlung in zwei Stufen:
1. **Schnell:** Erkannte Rechnungs-Mails (Betrag/Absender/Datum per Regex oder kleinem LLM-Prompt extrahiert) als Zeile in eine Nextcloud-Table "Spesen" schreiben — Tage, nicht Wochen Aufwand.
2. **Später, falls Tables nicht reicht:** Eigene Nextcloud-App (PHP, Nextcloud App-Framework) mit eigener UI/Workflow (Genehmigung, Kategorien, Export-Format für eure Buchhaltungssoftware) — KI-Mail-Helper würde dann nur noch strukturierte Daten per REST an diese App senden.

### B2. OpenProject — für "aus E-Mail wird Ticket/Task"

OpenProject hat eine vollständige REST-API v3 (JSON:API, Token-Auth). Sinnvollster Anwendungsfall: Auto-Rules-Engine um eine neue Aktion **"OpenProject Work Package anlegen"** erweitern (aktuell kann sie nur verschieben/markieren/taggen/Priorität setzen — die Engine ist dafür schon sauber strukturiert, siehe `AutoRulesEngine._execute_rule`). Priorität aus der 3×3-Matrix (Dringlichkeit×Wichtigkeit) auf OpenProject-Priorität mappen. Erkannte Work-Package-ID zurück an die E-Mail schreiben (verhindert Duplikate, zeigt "Tracked in OpenProject: WP#123" in der UI).

### B3. XWiki — eher Ergänzung als Kernfeature

Sinnvoll, falls ihr XWiki aktiv als internes Wissensmanagement nutzt: KI-generierte Zusammenfassungen wichtiger E-Mail-Threads (Entscheidungen, wiederkehrende Rückfragen) automatisch als Wiki-Seite in einem "Mail-Archiv"-Space ablegen, getaggt nach Absender/Thema. Niedrigere Priorität als A/B, da der Nutzen stark davon abhängt, wie aktiv ihr XWiki tatsächlich als Wissensbasis pflegt.

### B4. Architektur-Empfehlung: eine Integrationsschicht statt drei Einzel-Anbindungen

Statt drei separate Implementierungen zu bauen, würde ich der Auto-Rules-Engine **eine generische Aktion** hinzufügen: `"webhook"` bzw. `"external_action"` mit konfigurierbarem Ziel-Typ (Nextcloud-CalDAV, Nextcloud-Tables, OpenProject-API, generischer Webhook für z. B. n8n/Zapier-artige Weiterverarbeitung). Das macht die App zukunftsoffen für weitere Tools, ohne dass ihr für jedes neue Ziel-System die Rule-Engine erneut anfassen müsst. Aufwand nur unwesentlich höher als eine einzelne feste Nextcloud-Integration, aber deutlich wartbarer.

**Reihenfolge-Empfehlung:** B1 (Nextcloud Kalender + Tables) zuerst, da es auf eurer bestehenden Infrastruktur aufbaut und den größten sofortigen Nutzen bringt (Termine/Belege raus aus der Inbox); B4 (generische Aktion) direkt danach mitdenken, damit OpenProject/XWiki später ohne Refactoring dazukommen.

---

*Erstellt im Rahmen eines vollständigen Security-Reviews vor Produktiv-Gang. Alle als ✅ FIXED markierten Punkte sind in diesem Commit enthalten und kompilieren fehlerfrei; ein vollständiger Testlauf (`pytest`, inkl. Postgres/Redis/spaCy-Modellen) war in dieser Umgebung nicht möglich und sollte vor dem Merge nachgeholt werden.*
