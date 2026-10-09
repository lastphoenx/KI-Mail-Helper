"""DEK für Operator-Skripte — aus Masterpasswort (wie Login), nicht aus argv/env."""

from __future__ import annotations

import importlib
import sys

from src.services.audit_known_contacts_operator import OperatorDekError, dek_from_master_unlock


def resolve_dek_for_user_id(session, user_id: int) -> str:
    """Versteckte Passwort-Eingabe; leitet DEK über MasterKeyManager ab."""
    models = importlib.import_module(".02_models", "src")
    user = session.query(models.User).filter_by(id=user_id).first()
    if not user:
        raise OperatorDekError("user_not_found")
    if not sys.stdin.isatty():
        raise OperatorDekError("password_requires_tty")
    import getpass

    unlock = getpass.getpass("Masterpasswort (Eingabe verborgen): ")
    return dek_from_master_unlock(user, unlock)
