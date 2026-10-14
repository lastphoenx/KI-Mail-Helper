"""Welche Mail-Accounts IMAP-Protokoll (inkl. Microsoft 365 OAuth) nutzen."""

from __future__ import annotations

from sqlalchemy import and_, or_


def account_uses_imap_protocol(account) -> bool:
    if not account:
        return False
    if account.auth_type == "imap":
        return True
    return account.auth_type == "oauth" and account.oauth_provider == "microsoft"


def sqlalchemy_imap_account_filter(mail_account_model):
    """SQLAlchemy-Filter: klassisches IMAP oder Microsoft-365-OAuth (IMAP/XOAUTH2)."""
    return or_(
        mail_account_model.auth_type == "imap",
        and_(
            mail_account_model.auth_type == "oauth",
            mail_account_model.oauth_provider == "microsoft",
        ),
    )
