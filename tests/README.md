# Tests

## Nach Deploy (Audit / Tranco / Scam)

```bash
bash scripts/pytest-audit-smoke.sh
```

Das ist das **Release-Gate** laut `AGENTS.md` (~100 Tests, kein Legacy).

## Volle Suite `pytest tests/`

**Zähler:** `passed` + `skipped` ≠ «alles produktionsreif». **skipped** = bewusst ausgeklammerte Legacy-/Integrationsmodule (`tests/conftest.py`).

Erwartung auf CT (ohne `RUN_LEGACY_INTEGRATION`):

| Metrik | Bedeutung |
|--------|-----------|
| **passed** | Unit/Audit-Tests ohne Legacy-Block |
| **skipped** | Legacy (JSONB/SQLite, alte Mocks, Ollama, Mail-Fetcher, **`test_ai_client`**, …) |
| **failed** | echte offene Baustellen — nicht mit skipped vermischen |

| Symptom | Ursache | Aktion |
|--------|---------|--------|
| `JSONB` + `SQLiteTypeCompiler` | Modelle nutzen PostgreSQL-JSONB; Tests bauen `:memory:` SQLite | skipped (Legacy) |
| `[EMAIL]` vs `[EMAIL_1]` | Sanitizer-Tests veraltet | skipped / Ticket |
| `AutoRulesEngine` / `master_key` | Celery-Task-Tests nicht angepasst | skipped |
| `test_ai_client` | Ollama/Live-API, kein Deploy-Gate | **skipped** (wie Mail-Fetcher) |
| `test_mail_fetcher` / `no such table: users` | Alte `emails.db` im Repo-Root | **skipped** |

Optional Legacy erzwingen: `RUN_LEGACY_INTEGRATION=1 pytest tests/test_mail_fetcher.py -s`
