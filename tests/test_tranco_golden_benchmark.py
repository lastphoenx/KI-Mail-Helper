"""Golden-Set mit geladener Mini-Tranco-Fixture (kein Netz, keine echte Million)."""

from pathlib import Path

import pytest

from src.services.brand_domain_policy import effective_brand_map, find_brand_domain_mismatch
from src.services.audit_scam_detection import evaluate_scam_risk
from src.services.tranco_popularity import (
    build_sqlite_from_rank_pairs,
    get_tranco_store,
    is_well_known_domain,
    tranco_exempts_brand_mismatch,
)
from tests.scam_golden_set import ROWS
from tests.test_scam_golden_rules import _Meta


FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "tranco_mini.csv"


def _load_fixture_pairs() -> list[tuple[int, str]]:
    pairs: list[tuple[int, str]] = []
    for line in FIXTURE_CSV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rank_s, domain = line.split(",", 1)
        pairs.append((int(rank_s), domain.strip().lower()))
    return pairs


@pytest.fixture
def tranco_for_golden(tmp_path, monkeypatch):
    db = tmp_path / "tranco.db"
    build_sqlite_from_rank_pairs(_load_fixture_pairs(), db, list_id="GOLDEN-FIXTURE")
    monkeypatch.setenv("TRANCO_DB_PATH", str(db))
    monkeypatch.setenv("TRANCO_TOP_N", "100000")
    get_tranco_store(force_reload=True)
    yield
    get_tranco_store(force_reload=True)


def _meta_from_golden_row(row) -> _Meta:
    _, name, addr, subj, p, auth, _lu = row
    auth_results = (
        "dkim=none; dmarc=none; spf=pass"
        if auth == "none"
        else "dkim=pass; spf=pass; dmarc=pass"
    )
    return _Meta(
        subject=subj,
        sender=addr,
        sender_name=name,
        auth_results=auth_results,
        server_spam_flag=bool(p),
        provider_junk_score=10 if p else None,
    )


def test_fixture_csv_loads_and_well_known(tranco_for_golden):
    assert FIXTURE_CSV.is_file()
    assert is_well_known_domain("newsletter@derbund.ch")
    assert is_well_known_domain("noreply@sbb.ch")
    freemail = "g" + "mail.com"
    assert not is_well_known_domain(f"paypal.support@{freemail}")
    assert not is_well_known_domain("Swisscom-kundenbetreuung.ch/x@sendhost-demo.net")


def test_golden_non_scam_rows_still_not_scam_with_tranco(tranco_for_golden):
    """N/H/A: Tranco darf keine Falsch-Scams erzeugen (Regression)."""
    false_positives = []
    for row in ROWS:
        if row[0] not in ("N", "H", "A"):
            continue
        ev = evaluate_scam_risk(_meta_from_golden_row(row), llm_enabled=False)
        if ev.is_scam:
            false_positives.append(row[2])
    assert false_positives == [], false_positives[:5]


def test_golden_brand_impersonation_not_exempted_by_tranco(tranco_for_golden):
    """Marken-Treffer im Golden-Set: Tranco darf Mismatch nicht wegdämpfen."""
    brand_map = effective_brand_map(None)
    hits = 0
    for row in ROWS:
        if row[0] != "S":
            continue
        name, addr = row[1], row[2]
        hit = find_brand_domain_mismatch(name, addr, brand_map)
        if hit is None:
            continue
        hits += 1
        assert not tranco_exempts_brand_mismatch(name, addr), addr
    assert hits >= 8


def test_golden_e1_rows_still_scam_with_tranco(tranco_for_golden):
    for row in ROWS:
        if row[0] != "S" or "/" not in row[2].split("@")[0]:
            continue
        ev = evaluate_scam_risk(_meta_from_golden_row(row), llm_enabled=False)
        assert ev.is_scam, row[2]


def test_aligned_publisher_in_fixture_exempt_only_when_name_matches(tranco_for_golden):
    assert tranco_exempts_brand_mismatch("Der Bund — Tagesnews", "news@derbund.ch")
    assert not tranco_exempts_brand_mismatch("PostFinance", "news@derbund.ch")
