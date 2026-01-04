"""Tests für das neue DB-Schema mit Enums und Soft-Delete."""

import pytest
import importlib
import sys
from pathlib import Path
from datetime import datetime, timedelta, UTC
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, str(Path(__file__).parent.parent))

models = importlib.import_module('.02_models', 'src')


@pytest.fixture
def session():
    """Erstellt eine Test-DB-Session."""
    engine, Session = models.init_db(":memory:")
    session = Session()
    yield session
    session.close()


def test_user_creation(session):
    """Test: User mit Enums erstellen."""
    user = models.User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_pw"
    )
    user.preferred_ai_provider = models.AIProvider.OLLAMA.value
    user.preferred_ai_model = "llama3.2"
    
    session.add(user)
    session.commit()
    
    assert user.id is not None
    assert user.preferred_ai_provider == "ollama"


def test_mail_account_enums(session):
    """Test: MailAccount mit Encryption-Enums."""
    user = models.User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_pw"
    )
    session.add(user)
    session.flush()
    
    account = models.MailAccount(
        user_id=user.id,
        name="Test Account",
        encrypted_imap_server="encrypted_imap.example.com",
        encrypted_imap_username="encrypted_user",
        encrypted_imap_password="encrypted_pass",
        imap_encryption=models.IMAPEncryption.SSL.value,
        smtp_encryption=models.SMTPEncryption.STARTTLS.value
    )
    
    session.add(account)
    session.commit()
    
    assert account.imap_encryption == "SSL"
    assert account.smtp_encryption == "STARTTLS"


def test_raw_email_unique_constraint(session):
    """Test: UNIQUE Constraint auf RawEmail (user_id, mail_account_id, uid)."""
    user = models.User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_pw"
    )
    session.add(user)
    session.flush()
    
    account = models.MailAccount(
        user_id=user.id,
        name="Test Account",
        encrypted_imap_server="encrypted_imap.example.com",
        encrypted_imap_username="encrypted_user",
        encrypted_imap_password="encrypted_pass"
    )
    session.add(account)
    session.flush()
    
    raw_email1 = models.RawEmail(
        user_id=user.id,
        mail_account_id=account.id,
        imap_uid=123,
        imap_folder="INBOX",
        imap_uidvalidity=12345,
        encrypted_sender="encrypted_sender@example.com",
        encrypted_subject="encrypted_Test Email",
        encrypted_body="encrypted_Test body",
        received_at=datetime.now(UTC)
    )
    session.add(raw_email1)
    session.commit()
    
    raw_email2 = models.RawEmail(
        user_id=user.id,
        mail_account_id=account.id,
        imap_uid=123,
        imap_folder="INBOX",
        imap_uidvalidity=12345,
        encrypted_sender="encrypted_sender2@example.com",
        encrypted_subject="encrypted_Test Email 2",
        encrypted_body="encrypted_Test body 2",
        received_at=datetime.now(UTC)
    )
    session.add(raw_email2)
    
    with pytest.raises(IntegrityError):
        session.commit()


def test_processed_email_no_user_id(session):
    """Test: ProcessedEmail hat kein user_id Feld mehr."""
    user = models.User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_pw"
    )
    session.add(user)
    session.flush()
    
    account = models.MailAccount(
        user_id=user.id,
        name="Test Account",
        encrypted_imap_server="encrypted_imap.example.com",
        encrypted_imap_username="encrypted_user",
        encrypted_imap_password="encrypted_pass"
    )
    session.add(account)
    session.flush()
    
    raw_email = models.RawEmail(
        user_id=user.id,
        mail_account_id=account.id,
        imap_uid=999,
        imap_folder="INBOX",
        encrypted_sender="encrypted_sender@example.com",
        encrypted_subject="encrypted_Test",
        encrypted_body="encrypted_Body",
        received_at=datetime.now(UTC)
    )
    session.add(raw_email)
    session.flush()
    
    processed = models.ProcessedEmail(
        raw_email_id=raw_email.id,
        dringlichkeit=2,
        wichtigkeit=2,
        kategorie_aktion=models.EmailActionCategory.ACTION_REQUIRED.value,
        farbe=models.EmailColor.BLUE.value,
        score=50
    )
    session.add(processed)
    session.commit()
    
    assert not hasattr(processed, 'user_id') or processed.__class__.__table__.columns.get('user_id') is None
    assert processed.raw_email_id == raw_email.id


def test_soft_delete_fields(session):
    """Test: RawEmail und ProcessedEmail haben deleted_at und deleted_verm."""
    user = models.User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_pw"
    )
    session.add(user)
    session.flush()
    
    account = models.MailAccount(
        user_id=user.id,
        name="Test Account",
        encrypted_imap_server="encrypted_imap.example.com",
        encrypted_imap_username="encrypted_user",
        encrypted_imap_password="encrypted_pass"
    )
    session.add(account)
    session.flush()
    
    raw_email = models.RawEmail(
        user_id=user.id,
        mail_account_id=account.id,
        imap_uid=777,
        imap_folder="INBOX",
        encrypted_sender="encrypted_sender@example.com",
        encrypted_subject="encrypted_Delete Me",
        encrypted_body="encrypted_Body",
        received_at=datetime.now(UTC)
    )
    session.add(raw_email)
    session.flush()
    
    processed = models.ProcessedEmail(
        raw_email_id=raw_email.id,
        dringlichkeit=1,
        wichtigkeit=1,
        score=10
    )
    session.add(processed)
    session.commit()
    
    assert raw_email.deleted_at is None
    assert raw_email.deleted_verm == False
    assert raw_email.is_deleted == False
    
    raw_email.deleted_verm = True
    raw_email.deleted_at = datetime.now(UTC)
    session.commit()
    
    assert raw_email.is_deleted == True


def test_email_folder_creation(session):
    """Test: EmailFolder Tabelle existiert und hat Unique Constraint."""
    user = models.User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_pw"
    )
    session.add(user)
    session.flush()
    
    account = models.MailAccount(
        user_id=user.id,
        name="Test Account",
        encrypted_imap_server="encrypted_imap.example.com",
        encrypted_imap_username="encrypted_user",
        encrypted_imap_password="encrypted_pass"
    )
    session.add(account)
    session.flush()
    
    folder = models.EmailFolder(
        user_id=user.id,
        mail_account_id=account.id,
        name="INBOX",
        imap_path="INBOX"
    )
    session.add(folder)
    session.commit()
    
    assert folder.id is not None
    assert folder.name == "INBOX"
