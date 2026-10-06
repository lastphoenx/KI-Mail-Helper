#!/usr/bin/env bash
# Deploy-Smoke nach git pull (Produktion / lokal) — nicht die volle tests/-Suite.
# AGENTS.md: compileall + diese Tests reichen für Audit/Tranco/Scam-Änderungen.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python -m compileall -q src
exec python -m pytest -q \
  tests/test_src_compile_smoke.py \
  tests/test_tasks_import_modules.py \
  tests/test_tranco_popularity.py \
  tests/test_tranco_golden_benchmark.py \
  tests/test_tranco_update_security.py \
  tests/test_tranco_store_reload.py \
  tests/test_celery_tasks_registered.py \
  tests/test_rdap_lookup.py \
  tests/test_brand_health_rdap.py \
  tests/test_rdap_rate_limit.py \
  tests/test_scam_golden_rules.py \
  tests/test_brand_domain_policy.py \
  tests/test_spamhaus_dbl.py \
  tests/test_audit_scam_detection.py \
  tests/test_audit_safe_delete_veto.py \
  tests/test_identity_suspicion_auth.py \
  tests/test_audit_identity_refinements.py \
  "$@"
