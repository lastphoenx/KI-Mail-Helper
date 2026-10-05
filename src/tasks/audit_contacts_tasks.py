"""Celery: Bekannte Kontakte aus Gesendet einlesen."""

from __future__ import annotations

import logging

from src.celery_app import celery_app
from src.helpers.database import get_session, get_user, get_mail_account
from src.helpers.imap_fetcher_factory import build_imap_fetcher_for_account
from src.helpers.service_token_dek import (
    delete_service_token,
    get_dek_from_service_token,
)
from src.services.audit_contact_import import import_sent_contacts_for_account

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.audit_contacts.import_sent", max_retries=0)
def import_audit_known_contacts_task(
    self,
    user_id: int,
    account_id: int,
    service_token_id: int,
) -> dict:
    session = get_session()
    fetcher = None
    try:
        user = get_user(session, user_id)
        account = get_mail_account(session, account_id, user_id)
        if not user or not account:
            return {"success": False, "error": "not_found"}
        if not getattr(account, "audit_contacts_import_enabled", False):
            return {"success": False, "error": "import_disabled"}

        master_key = get_dek_from_service_token(service_token_id, session)
        if not master_key:
            return {"success": False, "error": "token"}

        fetcher = build_imap_fetcher_for_account(account, master_key)
        fetcher.connect()
        result = import_sent_contacts_for_account(
            session,
            fetcher,
            user_id=user_id,
            account_id=account_id,
        )
        return result
    except Exception as e:
        logger.exception("import_audit_known_contacts_task failed")
        return {"success": False, "error": type(e).__name__}
    finally:
        if fetcher:
            try:
                fetcher.disconnect()
            except Exception:
                pass
        delete_service_token(service_token_id, session)
        session.close()
