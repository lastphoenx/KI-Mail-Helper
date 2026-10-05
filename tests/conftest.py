# tests/conftest.py
"""Pytest Configuration & Shared Fixtures.

Implementiert pytest-Fixtures aus doc/Multi-User/03_CELERY_TEST_INFRASTRUCTURE.md
"""

import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# ===== DATABASE FIXTURES =====

@pytest.fixture(scope="session")
def test_database_url():
    """Test Database URL (uses SQLite by default, override with TEST_DATABASE_URL)."""
    return os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(scope="session")
def test_engine(test_database_url):
    """Create SQLAlchemy engine for testing."""
    engine = create_engine(
        test_database_url,
        connect_args={"check_same_thread": False} if test_database_url.startswith("sqlite") else {}
    )
    yield engine
    engine.dispose()


@pytest.fixture
def session(test_engine):
    """Database session for tests (auto-rollback after each test)."""
    from src.app_factory import SessionLocal
    connection = test_engine.connect()
    transaction = connection.begin()
    
    # Create session bound to connection
    Session = sessionmaker(bind=connection)
    session = Session()
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


# ===== CELERY FIXTURES (für Multi-User Migration) =====

@pytest.fixture(scope="session")
def celery_config():
    """Celery configuration for testing (uses fakeredis)."""
    return {
        "broker_url": "memory://",
        "result_backend": "cache+memory://",
        "task_always_eager": True,  # Execute tasks synchronously in tests
        "task_eager_propagates": True,  # Propagate exceptions
        "task_track_started": True,
        "result_expires": 3600,
    }


@pytest.fixture(scope="session")
def celery_enable_logging():
    """Enable Celery logging in tests."""
    return True


@pytest.fixture
def celery_app(celery_config):
    """Celery app instance for testing."""
    try:
        from src.celery_app import celery_app as app
        app.config_from_object(celery_config)
        yield app
    except ImportError:
        pytest.skip("Celery not installed or celery_app not configured")


# ===== FLASK APP FIXTURES =====

@pytest.fixture
def app():
    """Flask app instance for testing."""
    from src.app_factory import create_app
    app = create_app(config_name="testing")
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF for tests
    
    yield app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Flask CLI runner."""
    return app.test_cli_runner()


# ===== AUTHENTICATION FIXTURES =====

@pytest.fixture
def authenticated_user(client, session):
    """Create and login a test user."""
    from src.models import User
    from werkzeug.security import generate_password_hash
    
    # Create test user
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash=generate_password_hash("Test123!")
    )
    session.add(user)
    session.commit()
    
    # Login
    with client:
        client.post("/auth/login", data={
            "username": "testuser",
            "password": "Test123!"
        })
        yield user


# ===== LEGACY SUITE (volle pytest tests/ — nicht Deploy-Gate) =====

_LEGACY_TEST_FILES = frozenset(
    {
        "test_mail_fetcher.py",
        "test_mail_sync_tasks.py",
        "test_db_schema.py",
        "test_phase_y1.py",
        "test_phase_y2.py",
        "test_content_sanitizer.py",
        "test_integration_anonymization.py",
        "test_rule_execution_tasks.py",
        "test_ollama_inference.py",
        "test_ai_client.py",
    }
)


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_LEGACY_INTEGRATION"):
        return
    reason = (
        "Legacy/Integration-Test (SQLite/JSONB, alte Mocks). "
        "Deploy: bash scripts/pytest-audit-smoke.sh — oder RUN_LEGACY_INTEGRATION=1"
    )
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if item.path.name in _LEGACY_TEST_FILES:
            item.add_marker(skip)


# ===== CLEANUP FIXTURES =====

@pytest.fixture(autouse=True)
def cleanup_logs():
    """Clean up test logs after each test."""
    yield
    # Cleanup logic here if needed
