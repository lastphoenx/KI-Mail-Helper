"""Microsoft 365 OAuth-Helfer (ohne Live-Login)."""

import importlib


def test_microsoft_auth_url_contains_scopes():
    mod = importlib.import_module("src.11_microsoft_oauth")
    url = mod.MicrosoftOAuthManager.get_auth_url(
        client_id="test-client",
        redirect_uri="https://example.com/callback",
        state="abc",
    )
    assert "login.microsoftonline.com" in url
    assert "IMAP.AccessAsUser.All" in url
    assert "SMTP.Send" in url
    assert "state=abc" in url


def test_account_uses_imap_protocol_microsoft():
    from src.helpers.mail_account_imap import account_uses_imap_protocol

    class A:
        auth_type = "oauth"
        oauth_provider = "microsoft"

    class B:
        auth_type = "oauth"
        oauth_provider = "google"

    assert account_uses_imap_protocol(A())
    assert not account_uses_imap_protocol(B())
