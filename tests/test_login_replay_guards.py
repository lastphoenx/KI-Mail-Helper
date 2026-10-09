"""Login-Härtung: TOTP nur einmal, Recovery-Code nur einmal, neue Session."""
import hashlib
import importlib
import threading

import pyotp
from flask import Flask, jsonify, session
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.helpers.session_rotation import rotate_server_session

auth = importlib.import_module("src.07_auth")
models = importlib.import_module("src.02_models")


def test_totp_code_is_rejected_the_second_time():
    otp_seed = pyotp.random_base32()
    token = pyotp.TOTP(otp_seed).now()
    step = auth.AuthManager.matching_totp_step(otp_seed, token, None)
    assert step is not None
    assert auth.AuthManager.matching_totp_step(otp_seed, token, step) is None


def test_rotate_server_session_changes_the_cookie(tmp_path):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="a" * 32,
        SESSION_TYPE="filesystem",
        SESSION_FILE_DIR=str(tmp_path),
        SESSION_USE_SIGNER=True,
        SESSION_ID_LENGTH=32,
        TESTING=True,
    )
    Session(app)

    @app.route("/set")
    def _set():
        session["marker"] = "before"
        return "ok"

    @app.route("/rotate")
    def _rotate():
        old = session.sid
        session["pending_dek"] = "still-here"
        rotate_server_session()
        return jsonify(
            changed=session.sid != old,
            marker=session.get("marker"),
            kept=session.get("pending_dek"),
            old=old,
            new=session.sid,
        )

    client = app.test_client()
    client.get("/set")
    before = client.get_cookie("session")
    response = client.get("/rotate")
    after = client.get_cookie("session")
    body = response.get_json()
    assert body["changed"] is True
    assert body["marker"] == "before"
    assert body["kept"] == "still-here"
    assert before is not None and before != after

    def _stored(sid):
        name = hashlib.md5(f"session:{sid}".encode("utf-8")).hexdigest()
        return tmp_path / name

    assert not _stored(body["old"]).exists()
    assert _stored(body["new"]).exists()


def test_recovery_code_can_be_claimed_only_once():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.User.__table__.create(engine)
    models.RecoveryCode.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    user = models.User(username="ada", email="ada@example.com")
    user.set_password("testpassword123")
    db.add(user)
    db.commit()
    codes = auth.RecoveryCodeManager.create_recovery_codes(user.id, db, count=1)
    code = codes[0]
    user_id = user.id
    db.close()

    barrier = threading.Barrier(2)
    results = []

    def attempt():
        local = factory()
        barrier.wait()
        try:
            results.append(
                auth.RecoveryCodeManager.verify_recovery_code(user_id, code, local)
            )
        finally:
            local.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(True) == 1
    assert results.count(False) == 1
