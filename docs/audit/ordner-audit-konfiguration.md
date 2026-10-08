# Ordner-Audit — Konfiguration

Pro Mail-Konto. Die Oberfläche beschreibt Zweck und Beispiel. Hier steht, wo der Wert liegt.

Beispiele sind synthetisch (`example.com`, `Beispiel`). Keine echten Konten.

## Marken

| | |
|--|--|
| Zweck | Anzeigename und Absender-Domain müssen zur Marke passen. |
| Wirkung | Treffer ohne passende Domain wird Scam. «Domains prüfen» lehnt blockierte Domains ab. |
| Beispiel | Marke `Beispiel`, offizielle Domain `beispiel.example`. |
| Gespeichert | `audit_cluster_settings.brand_official_domains_json` (JSON, Marke → Domains). Health und DBL daneben in derselben Tabelle. |

## Meine Domains

| | |
|--|--|
| Zweck | Domains, die dem Konto gehören. |
| Wirkung | Keine Scam-Wertung als fremde Domain. Auth-Fehler und die feste Sicherheitsebene bleiben. Freemail wird nicht zur eigenen Domain. |
| Beispiel | `firma.example` |
| Gespeichert | `mail_accounts.audit_own_domains` (JSON-Liste) |

## Meine Adressen

| | |
|--|--|
| Zweck | Eine einzelne Absenderadresse. |
| Wirkung | Gilt nur für diese Adresse, nicht für die Domain. |
| Beispiel | `arbeit@example.com` |
| Gespeichert | `mail_accounts.audit_own_addresses` (JSON-Liste) |

## VIP

| | |
|--|--|
| Zweck | Absender, die wichtig bleiben. |
| Wirkung | Richtung «möglicherweise wichtig». Schaltet harte Scam-Signale nicht aus. |
| Beispiel | `person@firma.example` oder die Domain `firma.example` |
| Gespeichert | Tabelle `audit_vip_senders` |

## Wichtige Ordner

| | |
|--|--|
| Zweck | Ordner, die gescannt werden, aber nie «sicher löschbar» sind. |
| Wirkung | Genau dieser Ordner oder ein Unterordner (`path == Muster` oder `path` beginnt mit `Muster/`). `.` und `/` sind dasselbe Trennzeichen. `Dringend/Bank` trifft nicht `Dringend/Bank-Archiv` und nicht `Archiv/Bank`. Der reine Posteingang nie. |
| Beispiel | Haken bei `Dringend/Bank`. |
| Gespeichert | `mail_accounts.audit_curated_folder_patterns` (JSON-Liste der gewählten Pfade) |

## Aufbewahrung von Routine-Mails

| | |
|--|--|
| Zweck | Ab wann eine erkannte Routine-Mail sicher löschbar werden darf. |
| Wirkung | Ganze Tage, 1 bis 3650, pro Konto. Vorher Prüfen. Alarme nie. Erfolg über die Liste «Status- und Erfolgswörter», Versand über «Versand-Wörter». |
| Beispiel | «Backup successful» nach 30 Tagen. «Zugestellt» nach 30 Tagen. |
| Gespeichert | `mail_accounts.audit_success_safe_after_days`, `mail_accounts.audit_transaction_safe_after_days` |

## Wortlisten

| | |
|--|--|
| Zweck | Wörter im Betreff ergänzen oder ein festes Wort abschalten. |
| Wirkung | Vier Listen: `sensitive`, `alarm`, `success`, `shipping`. Systemwörter stehen im Code (`SENSITIVE_SUBJECT_TOKENS`, `OPERATIONAL_ALARM_TOKENS`, `SUCCESS_STATUS_TOKENS`, `TRANSACTION_STATUS_TOKENS`). Gespeichert werden nur Ergänzungen und Abschaltungen. Keine Tage pro Wort. |
| Beispiel | Eigenes Wort `fertig` bei Erfolg. `zugestellt` deaktivieren, wenn es falsch trifft. |
| Gespeichert | `mail_accounts.audit_word_lists_json` |

## Domain-Abfrage

| | |
|--|--|
| Zweck | Alter der Absender-Domain, nur im Zweifel. |
| Wirkung | Nicht das Alter der Mail. Jung plus Markenname kann Scam sein. Das zweite, höhere Limit setzt nur ein Badge. Aus: keine DNS/RDAP-Nachfrage. |
| Beispiel | Jung unter 30 Tagen mit Markenname: Scam. Hinweis unter 90 Tagen: Badge, kein Urteil. |
| Gespeichert | `mail_accounts.audit_domain_intel_enabled`, `audit_domain_young_days`, `audit_domain_caution_days`. Cache: `audit_domain_intel_cache`. |

## Bekannte Kontakte

Verschlüsselt wie Mails (DEK). Tabelle `audit_known_contacts`. Entscheidung und Betrieb: [ADR-audit-known-contacts-encryption.md](ADR-audit-known-contacts-encryption.md).

## Endnutzer

Dieselben Einstellungen in Alltagssprache: `docs/BENUTZERHANDBUCH.md` §12.
