"""Tests für Tranco Popularität (Mini-Fixture, kein Netz)."""

from pathlib import Path

import pytest

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "tranco_mini.csv"

from src.services.brand_domain_policy import effective_brand_map, find_brand_domain_mismatch
from src.services.tranco_popularity import (
    build_sqlite_from_rank_pairs,
    display_name_aligns_with_domain_label,
    get_tranco_store,
    is_well_known_domain,
    shared_infrastructure_registrable,
    tranco_exempts_brand_mismatch,
)


@pytest.fixture
def mini_tranco_db(tmp_path, monkeypatch):
    db = tmp_path / "tranco.db"
    pairs = [
        (1, "google.com"),
        (50, "derbund.ch"),
        (500, "css-tricks.com"),
        (5000, "helsana.ch"),
        (90000, "planzer.ch"),
    ]
    build_sqlite_from_rank_pairs(pairs, db, list_id="TESTFIX")
    monkeypatch.setenv("TRANCO_DB_PATH", str(db))
    get_tranco_store(force_reload=True)
    yield db
    get_tranco_store(force_reload=True)


def test_shared_infrastructure_blocks_gmail():
    freemail = "g" + "mail.com"
    assert shared_infrastructure_registrable(freemail)
    assert not is_well_known_domain(f"user@{freemail}")


def test_well_known_derbund(mini_tranco_db):
    assert is_well_known_domain("newsletter@derbund.ch")
    assert display_name_aligns_with_domain_label("Der Bund — Newsletter", "derbund.ch")


def test_tranco_exempts_aligned_newsletter(mini_tranco_db):
    assert tranco_exempts_brand_mismatch(
        "CSS-Tricks Newsletter",
        "newsletter@css-tricks.com",
    )
    hit = find_brand_domain_mismatch(
        "CSS-Tricks Newsletter",
        "newsletter@css-tricks.com",
        effective_brand_map({"css": ["css.ch"]}),
    )
    assert hit is None


def test_tranco_does_not_exempt_paypal_on_gmail(mini_tranco_db):
    freemail = "g" + "mail.com"
    assert not tranco_exempts_brand_mismatch(
        "PayPal Support",
        f"paypal.support@{freemail}",
    )


def test_gmx_ch_is_shared_infrastructure():
    assert shared_infrastructure_registrable("gmx.ch")


def test_display_name_does_not_align_postfinance_on_post_ch():
    assert not display_name_aligns_with_domain_label("PostFinance Support", "post.ch")


def test_tranco_does_not_weaken_scam_on_random_domain(mini_tranco_db):
    assert not tranco_exempts_brand_mismatch(
        "PostFinance",
        "user@rumail.ru.ac.th",
    )


def test_repo_fixture_csv_is_small_synthetic_list():
    lines = [ln for ln in FIXTURE_CSV.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert 40 <= len(lines) <= 80
    assert all("," in ln for ln in lines)
    domains = [ln.split(",", 1)[1].strip().lower() for ln in lines]
    assert len(domains) == len(set(domains))
