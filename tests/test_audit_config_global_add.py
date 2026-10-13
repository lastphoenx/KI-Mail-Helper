"""Cluster-Menü: mode=add ohne account_id speichert global (account_id NULL)."""

import importlib
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from flask import Flask
from flask_login import LoginManager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.blueprints.audit_config import audit_config_bp
from src.services.folder_audit_service import AuditConfigCache

models = importlib.import_module("src.02_models")


@pytest.fixture
def vip_global_add_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.User.__table__.create(engine)
    models.AuditVIPSender.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    user = models.User(username="audituser", email="audit@example.com")
    user.set_password("secret123!")
    db.add(user)
    db.commit()

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret-key-32-chars-minimum!!"
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def _load_user(user_id):
        return db.query(models.User).filter_by(id=int(user_id)).first()

    app.register_blueprint(audit_config_bp)

    @contextmanager
    def _db_ctx():
        yield db

    with patch("src.blueprints.audit_config.get_db_session", _db_ctx):
        with patch(
            "src.blueprints.audit_config.get_current_user_model",
            lambda _db: user,
        ):
            with patch.object(AuditConfigCache, "clear_cache"):
                with app.test_client() as client:
                    with client.session_transaction() as sess:
                        sess["_user_id"] = str(user.id)
                        sess["_fresh"] = True
                    yield client, db, user
    db.close()


def test_cluster_menu_vip_add_is_global_per_user(vip_global_add_client):
    client, db, user = vip_global_add_client
    resp = client.post(
        "/api/audit-config/vip-senders",
        json={"senders": "notify@example.com", "mode": "add"},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True

    row = (
        db.query(models.AuditVIPSender)
        .filter_by(user_id=user.id, sender_pattern="notify@example.com")
        .one()
    )
    assert row.account_id is None
    assert row.is_active is True
