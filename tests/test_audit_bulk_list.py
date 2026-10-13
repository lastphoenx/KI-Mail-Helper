"""Audit-Listen: mode=add vs. replace und Reaktivierung inaktiver user-Einträge."""

from types import SimpleNamespace

import pytest

from src.audit_bulk_list import bulk_mode_is_add_only, sync_user_list_values


def _row(value: str, active: bool = True, source: str = "user"):
    return SimpleNamespace(
        sender_pattern=value,
        is_active=active,
        source=source,
    )


def _active_values(rows):
    return sorted(r.sender_pattern for r in rows if r.is_active)


def test_add_mode_keeps_existing_and_appends_new():
    rows = [_row("a@example.com"), _row("b@example.com")]
    inserted = []

    def _insert(value: str) -> None:
        inserted.append(value)
        rows.append(_row(value))

    stats = sync_user_list_values(
        rows,
        ["c@example.com"],
        value_attr="sender_pattern",
        add_only=True,
        on_insert=_insert,
    )

    assert stats == {"added": 1, "reactivated": 0, "removed": 0, "total": 1}
    assert inserted == ["c@example.com"]
    assert _active_values(rows) == [
        "a@example.com",
        "b@example.com",
        "c@example.com",
    ]


def test_replace_mode_deactivates_missing_entries():
    rows = [_row("a@example.com"), _row("b@example.com")]

    def _insert(value: str) -> None:
        rows.append(_row(value))

    sync_user_list_values(
        rows,
        ["a@example.com", "c@example.com"],
        value_attr="sender_pattern",
        add_only=False,
        on_insert=_insert,
    )

    assert _active_values(rows) == ["a@example.com", "c@example.com"]
    assert rows[1].is_active is False


def test_replace_reactivates_soft_deleted_value():
    rows = [_row("a@example.com"), _row("b@example.com", active=False)]

    stats = sync_user_list_values(
        rows,
        ["b@example.com"],
        value_attr="sender_pattern",
        add_only=False,
        on_insert=lambda _v: None,
    )

    assert stats["reactivated"] == 1
    assert stats["added"] == 0
    assert rows[1].is_active is True
    assert rows[0].is_active is False


def test_add_mode_does_not_deactivate_others():
    rows = [_row("a@example.com"), _row("b@example.com")]

    sync_user_list_values(
        rows,
        ["c@example.com"],
        value_attr="sender_pattern",
        add_only=True,
        on_insert=lambda value: rows.append(_row(value)),
    )

    assert _active_values(rows) == [
        "a@example.com",
        "b@example.com",
        "c@example.com",
    ]


def test_bulk_mode_parsing():
    assert bulk_mode_is_add_only({}) is False
    assert bulk_mode_is_add_only({"mode": "add"}) is True
    assert bulk_mode_is_add_only({"mode": "replace"}) is False
    with pytest.raises(ValueError):
        bulk_mode_is_add_only({"mode": "merge"})
