# src/blueprints/__init__.py
"""Blueprint registration module.

This module exports all blueprints for registration in app_factory.py.
Each blueprint is imported from its own module file.

Blueprint Overview:
    auth_bp         - Authentication (7 routes): login, register, 2FA, logout
    emails_bp       - Email display (5 routes): dashboard, list, threads, detail
    email_actions_bp - Email actions (11 routes): done, undo, delete, move, etc.
    accounts_bp     - Account settings (22 routes): settings, mail accounts, OAuth
    tags_bp         - Tag management (2 routes): tags view, suggestions page
    api_bp          - API endpoints (64 routes): /api/* with prefix
    rules_bp        - Auto-rules (10 routes): rules management
    training_bp     - ML training (1 route): retrain models
    admin_bp        - Admin tools (1 route): debug logger status

Total: 123 routes across 9 blueprints
"""

from .auth import auth_bp
from .emails import emails_bp
from .email_actions import email_actions_bp
from .accounts import accounts_bp
from .tags import tags_bp
from .api import api_bp
from .rules import rules_bp
from .training import training_bp
from .admin import admin_bp

__all__ = [
    "auth_bp",
    "emails_bp",
    "email_actions_bp",
    "accounts_bp",
    "tags_bp",
    "api_bp",
    "rules_bp",
    "training_bp",
    "admin_bp",
]
