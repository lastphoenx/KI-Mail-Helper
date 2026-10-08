"""Alters-Bedingung der Auto-Action-Rules, ohne Konto und ohne Netzwerk."""

import secrets
from datetime import datetime, timedelta, timezone

from src.auto_rules_engine import (
    AutoRulesEngine,
    mail_is_older_than,
    parse_rule_age_days,
)


def _token() -> str:
    return "zw" + secrets.token_hex(4)


class _Rule:
    def __init__(self, conditions, actions=None):
        self.id = 3
        self.name = "alt"
        self.conditions = conditions
        self.actions = actions or {"delete": True}


def _mail(**kwargs):
    base = {
        "email_id": 7,
        "sender": "absender@example.com",
        "subject": f"Hinweis {_token()}",
        "body": "",
        "has_attachment": False,
        "folder": "INBOX",
        "received_at": datetime.now(timezone.utc) - timedelta(days=40),
    }
    base.update(kwargs)
    return base


def _engine():
    return AutoRulesEngine(user_id=1, master_key="x", db_session=None)


def test_age_days_are_whole_numbers_inside_the_limit():
    assert parse_rule_age_days(30) == 30
    assert parse_rule_age_days("12") == 12
    assert parse_rule_age_days(1) == 1
    assert parse_rule_age_days(3650) == 3650
    assert parse_rule_age_days(0) is None
    assert parse_rule_age_days(3651) is None
    assert parse_rule_age_days(1.5) is None
    assert parse_rule_age_days(True) is None
    assert parse_rule_age_days("12.5") is None
    assert parse_rule_age_days("") is None


def test_age_combines_with_subject_by_and_and_or():
    word = _token()
    engine = _engine()
    old = _mail(subject=f"Notiz {word}", received_at=datetime.now(timezone.utc) - timedelta(days=40))
    young = _mail(
        email_id=8,
        subject=f"Notiz {word}",
        received_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    old_other = _mail(
        email_id=9,
        subject=f"Andere {_token()}",
        received_at=datetime.now(timezone.utc) - timedelta(days=40),
    )
    undated = _mail(email_id=10, subject=f"Notiz {word}", received_at=None)

    both = _Rule({
        "match_mode": "all",
        "subject_contains": word,
        "older_than_days": 30,
    })
    either = _Rule({
        "match_mode": "any",
        "subject_contains": word,
        "older_than_days": 30,
    })

    assert engine._match_rule(both, old).matched
    assert not engine._match_rule(both, young).matched
    assert not engine._match_rule(both, old_other).matched
    assert not engine._match_rule(both, undated).matched
    assert engine._match_rule(either, young).matched
    assert engine._match_rule(either, old_other).matched
    assert not engine._match_rule(either, _mail(
        email_id=11,
        subject=f"Andere {_token()}",
        received_at=datetime.now(timezone.utc) - timedelta(days=3),
    )).matched
    assert not mail_is_older_than(None, 30)


def test_preview_lists_old_mail_and_does_not_run_the_delete():
    engine = _engine()
    rule = _Rule({"older_than_days": 30}, actions={"delete": True})
    old = _mail(email_id=21, subject=f"Alt {_token()}")
    young = _mail(
        email_id=22,
        subject=f"Neu {_token()}",
        received_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    hits = engine.preview_matching_mails(rule, [old, young])
    assert [row["email_id"] for row in hits] == [21]
    assert hits[0]["subject"] == old["subject"]
    assert hits[0]["age_days"] >= 30
    assert hits[0]["actions_would_execute"] == ["delete"]
    assert "received_at" in hits[0]
