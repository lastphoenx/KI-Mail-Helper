"""IMAP MailFetcher für Mail-Accounts (entschlüsselte Credentials)."""

import importlib


def build_imap_fetcher_for_account(account, master_key):
    encryption = importlib.import_module(".08_encryption", "src")
    mail_fetcher_mod = importlib.import_module(".06_mail_fetcher", "src")

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
