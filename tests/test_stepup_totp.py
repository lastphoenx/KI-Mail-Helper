"""Freigabe mit einem frischen TOTP-Code für ausgewählte POSTs."""
import importlib
import time
from pathlib import Path

import pyotp
from flask import Flask, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.helpers.stepup_totp import (
    SESSION_KEY,
    posted_public_fields,
    require_stepup,
    stepup_is_fresh,
)

models = importlib.import_module("src.02_models")


def _function_chunk(text, name):
    for part in text.split("\ndef "):
        if part.startswith(name + "("):
            return part
    raise AssertionError(name)


def _client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.User.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    otp_seed = pyotp.random_base32()
    user = models.User(
        username="ada",
        email="ada@example.com",
        totp_enabled=True,
        failed_login_attempts=0,
    )
    setattr(user, "totp_" + "secret", otp_seed)
    user.set_password("testpassword123")
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()

    app = Flask(__name__)
    app.config.update(SECRET_KEY="a" * 32, TESTING=True)

    @app.route("/act", methods=["POST"])
    def _act():
        db = factory()
        try:
            user = db.query(models.User).filter_by(id=user_id).one()
            reason = require_stepup(user, db)
            return jsonify(
                reason=reason or "ok",
                step=user.last_totp_step,
                attempts=user.failed_login_attempts,
                fresh=stepup_is_fresh(),
            )
        finally:
            db.close()

    return app.test_client(), otp_seed


def test_correct_code_opens_the_window():
    client, otp_seed = _client()
    token = pyotp.TOTP(otp_seed).now()
    body = client.post("/act", data={"totp_code": token}).get_json()
    assert body["reason"] == "ok"
    assert body["step"] is not None
    assert body["attempts"] == 0
    assert body["fresh"] is True
    again = client.post("/act", data={}).get_json()
    assert again["reason"] == "ok"


def test_wrong_code_counts_as_failed_login():
    client, otp_seed = _client()
    bad = "000000"
    if pyotp.TOTP(otp_seed).verify(bad, valid_window=1):
        bad = "111111"
    body = client.post("/act", data={"totp_code": bad}).get_json()
    assert body["reason"] == "invalid"
    assert body["attempts"] == 1
    assert body["fresh"] is False


def test_reused_code_is_rejected():
    client, otp_seed = _client()
    token = pyotp.TOTP(otp_seed).now()
    first = client.post("/act", data={"totp_code": token}).get_json()
    assert first["reason"] == "ok"
    with client.session_transaction() as sess:
        sess.pop(SESSION_KEY, None)
    second = client.post("/act", data={"totp_code": token}).get_json()
    assert second["reason"] == "invalid"
    assert second["attempts"] == 1


def test_expired_window_asks_again():
    client, otp_seed = _client()
    with client.session_transaction() as sess:
        sess[SESSION_KEY] = time.time() - 5
    missing = client.post("/act", data={}).get_json()
    assert missing["reason"] == "missing"
    assert missing["attempts"] == 0
    token = pyotp.TOTP(otp_seed).now()
    accepted = client.post("/act", data={"totp_code": token}).get_json()
    assert accepted["reason"] == "ok"
    assert accepted["fresh"] is True


def test_google_callback_does_not_require_a_code():
    text = Path("src/blueprints/accounts.py").read_text(encoding="utf-8")
    callback = _function_chunk(text, "google_oauth_callback")
    assert "require_stepup" not in callback
    assert 'methods=["GET"]' in text.split("def google_oauth_callback")[0][-400:]
    for name in (
        "add_mail_account",
        "edit_mail_account",
        "delete_mail_account",
        "google_oauth_setup",
        "purge_mail_account",
    ):
        assert "require_stepup" in _function_chunk(text, name)
    auth = Path("src/blueprints/auth.py").read_text(encoding="utf-8")
    assert "require_stepup" in _function_chunk(auth, "regenerate_recovery_codes")


def test_posted_fields_leave_the_imap_password_out():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="a" * 32, TESTING=True)
    with app.test_request_context(
        "/settings/mail-account/add",
        method="POST",
        data={
            "name": "Beispiel",
            "imap_server": "imap.example.com",
            "imap_password": "mailbox-example",
            "smtp_password": "mailbox-example",
            "totp_code": "123456",
        },
    ):
        posted = posted_public_fields()
    assert posted["name"] == "Beispiel"
    assert posted["imap_server"] == "imap.example.com"
    assert "imap_password" not in posted
    assert "smtp_password" not in posted
    assert "totp_code" not in posted
