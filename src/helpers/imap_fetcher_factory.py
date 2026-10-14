"""IMAP MailFetcher für Mail-Accounts (Passwort oder Microsoft 365 OAuth)."""

import importlib

from src.helpers.mail_account_imap import account_uses_imap_protocol


def build_imap_fetcher_for_account(account, master_key, db_session=None):
    encryption = importlib.import_module(".08_encryption", "src")
    mail_fetcher_mod = importlib.import_module(".06_mail_fetcher", "src")

    if not account_uses_imap_protocol(account):
        raise ValueError("Account unterstützt kein IMAP-Protokoll")

    if account.auth_type == "oauth" and account.oauth_provider == "microsoft":
        microsoft_oauth = importlib.import_module(".11_microsoft_oauth", "src")
        bearer = microsoft_oauth.MicrosoftOAuthTokenManager.ensure_fresh_bearer(
            account, master_key, db_session=db_session
        )
        if not bearer:
            raise ValueError("Microsoft OAuth: Token konnte nicht erneuert werden")
        imap_server = encryption.CredentialManager.decrypt_server(
            account.encrypted_imap_server, master_key
        )
        imap_username = encryption.CredentialManager.decrypt_email_address(
            account.encrypted_imap_username, master_key
        )
        return mail_fetcher_mod.MailFetcher.for_oauth2(
            server=imap_server,
            username=imap_username,
            bearer=bearer,
            port=account.imap_port or 993,
        )

    imap_server = encryption.CredentialManager.decrypt_server(
        account.encrypted_imap_server, master_key
    )
    imap_username = encryption.CredentialManager.decrypt_email_address(
        account.encrypted_imap_username, master_key
    )
    imap_password = encryption.CredentialManager.decrypt_imap_password(
        account.encrypted_imap_password, master_key
    )

    return mail_fetcher_mod.MailFetcher(
        server=imap_server,
        username=imap_username,
        password=imap_password,
        port=account.imap_port,
    )
