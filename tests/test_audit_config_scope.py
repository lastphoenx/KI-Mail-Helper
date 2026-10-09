"""Zählung der Audit-Listen: ohne Konto nur globale Zeilen, mit Konto global plus dieses Konto."""

import importlib

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.audit_list_scope import apply_account_scope

db_models = importlib.import_module("src.02_models")
AuditVIPSender = db_models.AuditVIPSender


def _session():
    engine = create_engine("sqlite:///:memory:")
    AuditVIPSender.__table__.create(engine)
    return sessionmaker(bind=engine)()


def _vip(session, pattern, account_id):
    session.add(
        AuditVIPSender(
            user_id=1,
            account_id=account_id,
            sender_pattern=pattern,
            pattern_type="exact",
            source="user",
            is_active=True,
        )
    )


def _count(session, account_id):
    query = session.query(AuditVIPSender).filter(
        AuditVIPSender.user_id == 1,
        AuditVIPSender.is_active == True,
    )
    return apply_account_scope(query, AuditVIPSender.account_id, account_id).count()


def test_vip_count_is_global_without_account_and_global_plus_account_with_one():
    session = _session()
    _vip(session, "global@example.com", None)
    _vip(session, "konto@example.com", 7)
    _vip(session, "anderes@example.com", 8)
    session.commit()

    assert _count(session, None) == 1
    assert _count(session, 7) == 2
    assert _count(session, 8) == 2
