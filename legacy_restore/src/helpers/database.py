# src/helpers/database.py
"""Database session helpers for all blueprints.

Extracted from 01_web_app.py lines 399-414.
"""

from contextlib import contextmanager
from flask_login import current_user
import importlib
import os

# Lazy imports to avoid circular dependencies
_SessionLocal = None
_models = None
_engine = None


def _get_engine():
    """Get or create SQLAlchemy engine (cached).
    
    Supports both SQLite and PostgreSQL based on DATABASE_URL.
    SQLite: Uses check_same_thread and timeout connect_args
    PostgreSQL: Uses connection pooling for multi-user scenarios
    """
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine
        DATABASE_PATH = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
            "emails.db"
        )
        DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")
        
        # Dialect-aware Engine Configuration
        if DATABASE_URL.startswith("sqlite"):
            # SQLite: Single-file, thread-safety settings
            _engine = create_engine(
                DATABASE_URL,
                connect_args={"check_same_thread": False, "timeout": 30.0}
            )
        else:
            # PostgreSQL/MySQL: Connection pooling for multi-user
            _engine = create_engine(
                DATABASE_URL,
                pool_size=20,
                max_overflow=40,
                pool_recycle=3600,
                connect_args={"connect_timeout": 10}
            )
    return _engine


def _get_session_local():
    """Get or create SQLAlchemy SessionLocal factory (cached)."""
    global _SessionLocal
    if _SessionLocal is None:
        from sqlalchemy.orm import sessionmaker
        _SessionLocal = sessionmaker(bind=_get_engine())
    return _SessionLocal


def _get_models():
    """Lazy load models module to avoid circular imports."""
    global _models
    if _models is None:
        _models = importlib.import_module(".02_models", "src")
    return _models


@contextmanager
def get_db_session():
    """Context manager for database sessions.
    
    Usage:
        with get_db_session() as db:
            user = db.query(User).first()
    
    Yields:
        SQLAlchemy session that auto-closes on exit
    """
    SessionLocal = _get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_model(db):
    """Get the current user's database model.
    
    Args:
        db: SQLAlchemy session
        
    Returns:
        User model instance or None if not authenticated
    """
    if not current_user.is_authenticated:
        return None
    models = _get_models()
    return db.query(models.User).filter_by(id=current_user.id).first()


# =============================================================================
# CELERY TASK HELPERS
# =============================================================================
# Diese Funktionen sind für Celery Tasks konzipiert, die außerhalb des
# Flask Request-Kontexts laufen und daher keinen Zugriff auf current_user haben.
# =============================================================================

def get_session():
    """Get a new database session for Celery tasks.
    
    Unlike get_db_session(), this returns a raw session without context manager.
    The caller is responsible for calling session.close() in a finally block!
    
    Usage in Celery tasks:
        session = get_session()
        try:
            user = get_user(session, user_id)
            # ... do work ...
        finally:
            session.close()  # WICHTIG!
    
    Returns:
        SQLAlchemy Session instance
    """
    SessionLocal = _get_session_local()
    return SessionLocal()


def get_user(session, user_id: int):
    """Get user by ID for Celery task validation.
    
    Args:
        session: SQLAlchemy session
        user_id: ID of the user to retrieve
        
    Returns:
        User model instance or None if not found
    """
    models = _get_models()
    return session.query(models.User).filter_by(id=user_id).first()


def get_mail_account(session, account_id: int, user_id: int):
    """Get mail account with ownership validation.
    
    Security: Returns None if account doesn't belong to the specified user!
    This prevents cross-user data access in multi-user scenarios.
    
    Args:
        session: SQLAlchemy session
        account_id: ID of the mail account
        user_id: ID of the user (ownership check)
        
    Returns:
        MailAccount model instance or None if not found/unauthorized
    """
    models = _get_models()
    return session.query(models.MailAccount).filter_by(
        id=account_id, 
        user_id=user_id  # Security: Ownership Check!
    ).first()
