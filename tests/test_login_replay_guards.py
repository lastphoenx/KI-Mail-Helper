"""Login-Härtung: TOTP nur einmal, Recovery-Code nur einmal, neue Session."""
import base64
import hashlib
import importlib
import os
import threading

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

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
        rotate_server_session()
        session["marker"] = "after"
        return jsonify(changed=session.sid != old, marker=session.get("marker"))

    client = app.test_client()
    client.get("/set")
    before = client.get_cookie("session")
    response = client.get("/rotate")
    after = client.get_cookie("session")
    body = response.get_json()
    assert body["changed"] is True
    assert body["marker"] == "after"
    assert before is not None and before != after


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


def _blob_at_rounds(password, master_key, rounds):
    salt = os.urandom(16)
    iv = os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)[:32]
    encryptor = Cipher(algorithms.AES(key), modes.GCM(iv)).encryptor()
    ciphertext = encryptor.update(master_key.encode()) + encryptor.finalize()
    return ":".join(
        base64.b64encode(part).decode()
        for part in (salt, iv, ciphertext, encryptor.tag)
    )


def test_legacy_100k_key_is_rewrapped_at_600k():
    encryption = importlib.import_module("src.08_encryption")
    phrase = "correct-horse-example"
    master_key = base64.b64encode(b"k" * 32).decode()
    blob = _blob_at_rounds(phrase, master_key, 100000)

    engine = create_engine("sqlite://")
    models.User.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    user = models.User(username="ada", email="ada@example.com")
    user.set_password(phrase)
    user.encrypted_master_key = blob
    user.encrypted_dek = None
    db.add(user)
    db.commit()

    opened = auth.MasterKeyManager.decrypt_dek_from_password(user, phrase, db)
    assert opened == master_key
    assert user.encrypted_master_key is None
    kek = encryption.EncryptionManager.generate_master_key(phrase, user.salt)
    assert encryption.EncryptionManager.decrypt_dek(user.encrypted_dek, kek) == master_key
    db.close()
