"""
Unit Tests für Phase Y1: Config Manager & Ensemble Combiner
"""

import pytest
import json
from datetime import datetime, UTC
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import importlib.util

# Dynamischer Import von 02_models.py
spec = importlib.util.spec_from_file_location(
    "models", "/home/thomas/projects/KI-Mail-Helper/src/02_models.py"
)
db_models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db_models)

from src.services.spacy_config_manager import SpacyConfigManager
from src.services.ensemble_combiner import EnsembleCombiner

Base = db_models.Base
User = db_models.User
MailAccount = db_models.MailAccount
SpacyVIPSender = db_models.SpacyVIPSender
SpacyKeywordSet = db_models.SpacyKeywordSet
SpacyScoringConfig = db_models.SpacyScoringConfig
SpacyUserDomain = db_models.SpacyUserDomain
ProcessedEmail = db_models.ProcessedEmail
RawEmail = db_models.RawEmail


@pytest.fixture
def db_session():
    """In-Memory SQLite DB für Tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def test_user(db_session):
    """Erstellt Test-User."""
    user = User(username="testuser", email="test@example.com")
    user.set_password("testpassword123")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_account(db_session, test_user):
    """Erstellt Test Mail-Account."""
    account = MailAccount(
        user_id=test_user.id,
        name="Test Account",
        auth_type="imap",
        urgency_booster_enabled=True,
    )
    db_session.add(account)
    db_session.commit()
    return account


# ===== SPACY CONFIG MANAGER TESTS =====


def test_load_empty_config(db_session, test_account):
    """Test: Leere Config lädt Default-Werte."""
    manager = SpacyConfigManager(db_session)
    config = manager.load_account_config(test_account.id)

    assert "vip_senders" in config
    assert "keyword_sets" in config
    assert "scoring_config" in config
    assert "user_domains" in config

    # Default Keywords sollten geladen sein
    assert len(config["keyword_sets"]) == 12
    assert "imperative_verbs" in config["keyword_sets"]
    assert "prüfen" in config["keyword_sets"]["imperative_verbs"]


def test_vip_sender_detection(db_session, test_account):
    """Test: VIP-Absender wird erkannt."""
    # VIP einfügen
    vip = SpacyVIPSender(
        account_id=test_account.id,
        sender_pattern="boss@example.com",
        pattern_type="email",
        importance_boost=5,
        description="CEO",
    )
    db_session.add(vip)
    db_session.commit()

    manager = SpacyConfigManager(db_session)

    # VIP sollte erkannt werden
    boost = manager.get_vip_boost(test_account.id, "boss@example.com")
    assert boost == 5

    # Nicht-VIP sollte 0 zurückgeben
    boost_none = manager.get_vip_boost(test_account.id, "nobody@example.com")
    assert boost_none == 0


def test_vip_domain_detection(db_session, test_account):
    """Test: VIP-Domain wird erkannt."""
    # VIP-Domain einfügen
    vip = SpacyVIPSender(
        account_id=test_account.id,
        sender_pattern="vip-company.com",
        pattern_type="domain",
        importance_boost=3,
    )
    db_session.add(vip)
    db_session.commit()

    manager = SpacyConfigManager(db_session)

    # Jede Email von dieser Domain sollte Boost bekommen
    boost = manager.get_vip_boost(test_account.id, "anyone@vip-company.com")
    assert boost == 3


def test_internal_email_detection(db_session, test_account):
    """Test: Interne/Externe Email Detection."""
    # User-Domain hinzufügen
    domain = SpacyUserDomain(
        account_id=test_account.id, domain="mycompany.com", is_active=True
    )
    db_session.add(domain)
    db_session.commit()

    manager = SpacyConfigManager(db_session)

    # Interne Email
    assert manager.is_internal_email(test_account.id, "colleague@mycompany.com") == True

    # Externe Email
    assert manager.is_internal_email(test_account.id, "client@external.com") == False


def test_custom_keyword_sets(db_session, test_account):
    """Test: Custom Keyword-Sets werden geladen."""
    # Custom Keywords einfügen
    keyword_set = SpacyKeywordSet(
        account_id=test_account.id,
        keyword_set_name="custom_urgency",
        keywords_json=json.dumps(["custom1", "custom2", "custom3"]),
        is_active=True,
    )
    db_session.add(keyword_set)
    db_session.commit()

    manager = SpacyConfigManager(db_session)
    keywords = manager.get_keywords(test_account.id, "custom_urgency")

    assert len(keywords) == 3
    assert "custom1" in keywords


def test_scoring_config_defaults(db_session, test_account):
    """Test: Default Scoring-Config."""
    manager = SpacyConfigManager(db_session)
    config = manager.load_account_config(test_account.id)

    scoring = config["scoring_config"]
    assert scoring["imperative_weight"] == 3
    assert scoring["deadline_weight"] == 4
    assert scoring["vip_weight"] == 3
    assert scoring["spacy_weight_initial"] == 100


def test_config_caching(db_session, test_account):
    """Test: Config wird gecached."""
    manager = SpacyConfigManager(db_session)

    # Erste Abfrage
    config1 = manager.load_account_config(test_account.id)
    # Zweite Abfrage (sollte aus Cache kommen)
    config2 = manager.load_account_config(test_account.id)

    assert config1 is config2  # Gleiche Objekt-Referenz


# ===== ENSEMBLE COMBINER TESTS =====


def test_ensemble_weights_initial_phase(db_session, test_account):
    """Test: Initial Phase (<20 Korrekturen) → 100% spaCy."""
    combiner = EnsembleCombiner(db_session)
    spacy_weight, sgd_weight = combiner._get_weights(num_corrections=10)

    assert spacy_weight == 100
    assert sgd_weight == 0


def test_ensemble_weights_learning_phase(db_session, test_account):
    """Test: Learning Phase (20-50 Korrekturen) → 30% spaCy + 70% SGD."""
    combiner = EnsembleCombiner(db_session)
    spacy_weight, sgd_weight = combiner._get_weights(num_corrections=30)

    assert spacy_weight == 30
    assert sgd_weight == 70


def test_ensemble_weights_trained_phase(db_session, test_account):
    """Test: Trained Phase (50+ Korrekturen) → 15% spaCy + 85% SGD."""
    combiner = EnsembleCombiner(db_session)
    spacy_weight, sgd_weight = combiner._get_weights(num_corrections=60)

    assert spacy_weight == 15
    assert sgd_weight == 85


def test_combine_predictions(db_session, test_account):
    """Test: spaCy + SGD Predictions werden kombiniert."""
    combiner = EnsembleCombiner(db_session)

    spacy_scores = {"wichtigkeit": 3, "dringlichkeit": 2}
    sgd_scores = {"wichtigkeit": 5, "dringlichkeit": 4}

    # Learning Phase (30% spaCy + 70% SGD)
    final = combiner.combine_predictions(
        account_id=test_account.id,
        spacy_scores=spacy_scores,
        sgd_scores=sgd_scores,
        num_corrections=30,
    )

    # Erwartung: (3*30 + 5*70)/100 = 4.3 → 4
    assert final["wichtigkeit"] == 4
    # (2*30 + 4*70)/100 = 3.4 → 3
    assert final["dringlichkeit"] == 3


def test_correction_count_zero(db_session, test_account):
    """Test: Keine Korrekturen → Count = 0."""
    combiner = EnsembleCombiner(db_session)
    count = combiner.get_correction_count(test_account.id)
    assert count == 0


def test_correction_count_with_overrides(db_session, test_user, test_account):
    """Test: User-Korrekturen werden gezählt."""
    # Raw Email erstellen
    raw = RawEmail(
        user_id=test_user.id,
        mail_account_id=test_account.id,
        encrypted_sender="test@example.com",
        encrypted_subject="Test",
        encrypted_body="Test body",
        received_at=datetime.now(UTC),
        message_id="test123",
    )
    db_session.add(raw)
    db_session.commit()

    # Processed Email mit Korrektur
    processed = ProcessedEmail(
        raw_email_id=raw.id,
        kategorie_aktion="info",
        dringlichkeit=2,
        wichtigkeit=3,
        user_override_dringlichkeit=5,  # User-Korrektur!
    )
    db_session.add(processed)
    db_session.commit()

    combiner = EnsembleCombiner(db_session)
    count = combiner.get_correction_count(test_account.id)
    assert count == 1


def test_learning_phase_detection(db_session, test_account):
    """Test: Learning Phase wird korrekt erkannt."""
    combiner = EnsembleCombiner(db_session)

    assert combiner.get_learning_phase(10) == "initial"
    assert combiner.get_learning_phase(30) == "learning"
    assert combiner.get_learning_phase(60) == "trained"


def test_sgd_trigger_threshold(db_session, test_account):
    """Test: SGD wird ab 20 Korrekturen aktiviert."""
    combiner = EnsembleCombiner(db_session)

    assert combiner.should_trigger_sgd_learning(19) == False
    assert combiner.should_trigger_sgd_learning(20) == True
    assert combiner.should_trigger_sgd_learning(50) == True


def test_ensemble_stats(db_session, test_account):
    """Test: Ensemble-Stats werden korrekt zurückgegeben."""
    combiner = EnsembleCombiner(db_session)
    stats = combiner.get_ensemble_stats(test_account.id)

    assert "num_corrections" in stats
    assert "learning_phase" in stats
    assert "spacy_weight" in stats
    assert "sgd_weight" in stats
    assert "sgd_enabled" in stats

    assert stats["num_corrections"] == 0
    assert stats["learning_phase"] == "initial"
    assert stats["spacy_weight"] == 100
    assert stats["sgd_weight"] == 0
    assert stats["sgd_enabled"] == False


# ===== INTEGRATION TESTS =====


def test_full_ensemble_workflow_initial(db_session, test_account):
    """Test: Kompletter Ensemble-Workflow (Initial Phase)."""
    combiner = EnsembleCombiner(db_session)

    spacy_result = {"wichtigkeit": 3, "dringlichkeit": 2, "details": {}}

    # Keine Korrekturen → Initial Phase → Nur spaCy
    final = combiner.compute_final_scores(
        account_id=test_account.id,
        email_content="Test email",
        spacy_pipeline_result=spacy_result,
        sgd_classifier=None,  # SGD nicht verfügbar
    )

    assert final["wichtigkeit"] == 3
    assert final["dringlichkeit"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
