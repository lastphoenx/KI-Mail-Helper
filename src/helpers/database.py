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
    """Get or create SQLAlchemy engine (cached)."""
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine
        DATABASE_PATH = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
            "emails.db"
        )
        DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")
        _engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False, "timeout": 30.0}
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
