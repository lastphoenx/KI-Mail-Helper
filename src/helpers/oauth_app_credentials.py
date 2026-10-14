"""OAuth-App Client-ID/Secret verschlüsselt auf MailAccount (SMTP-Felder, kein Klartext-Passwort)."""

import importlib


def store_oauth_app_credentials(account, app_id: str, ms_app_key: str, master_key: str) -> None:
    encryption = importlib.import_module(".08_encryption", "src")
    enc_id = encryption.CredentialManager.encrypt_email_address(app_id.strip(), master_key)
    enc_key = encryption.CredentialManager.encrypt_imap_password(ms_app_key.strip(), master_key)
    setattr(account, "encrypted_smtp_username", enc_id)
    setattr(account, "encrypted_smtp_password", enc_key)


def load_oauth_app_credentials(account, master_key: str) -> tuple[str, str]:
    encryption = importlib.import_module(".08_encryption", "src")
    if not account.encrypted_smtp_username or not account.encrypted_smtp_password:
        return "", ""
    app_id = encryption.CredentialManager.decrypt_email_address(
        account.encrypted_smtp_username, master_key
    )
    ms_app_key = encryption.CredentialManager.decrypt_imap_password(
        account.encrypted_smtp_password, master_key
    )
    return app_id, ms_app_key
