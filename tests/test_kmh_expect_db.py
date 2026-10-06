"""Tests: kmh_expect_db (current_database vs --expect-db)."""

from __future__ import annotations

import pytest

from scripts.kmh_expect_db import ExpectDbMismatch, check_expect_db, current_database_name


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _PgSession:
    def get_bind(self):
        return type("B", (), {"dialect": type("D", (), {"name": "postgresql"})(), "url": None})()

    def execute(self, _stmt):
        return _FakeResult("mail_helper_drill")


def test_check_expect_db_ok():
    check_expect_db(_PgSession(), "mail_helper_drill")


def test_check_expect_db_mismatch():
    with pytest.raises(ExpectDbMismatch) as exc:
        check_expect_db(_PgSession(), "mail_helper")
    assert exc.value.actual == "mail_helper_drill"
    assert exc.value.expected == "mail_helper"


def test_current_database_name_postgresql():
    assert current_database_name(_PgSession()) == "mail_helper_drill"
