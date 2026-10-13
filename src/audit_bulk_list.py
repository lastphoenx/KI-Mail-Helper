"""Gemeinsame Logik für Audit-Listen (Bulk-Ersetzen vs. Hinzufügen, Soft-Delete-Reaktivierung)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def bulk_mode_is_add_only(data: dict[str, Any]) -> bool:
    mode = str(data.get("mode") or "replace").strip().lower()
    if mode not in ("add", "replace"):
        raise ValueError("mode muss 'add' oder 'replace' sein")
    return mode == "add"


def sync_user_list_values(
    existing_rows: list[Any],
    new_values: list[str],
    *,
    value_attr: str,
    add_only: bool,
    on_insert: Callable[[str], None],
) -> dict[str, int]:
    """Synchronisiert user-Quell-Einträge mit einer Werteliste.

    - Neue Werte: anlegen (on_insert).
    - Bereits vorhandene, inaktive: is_active=True.
    - replace-Modus: user-Einträge nicht in new_values -> is_active=False.
    - add_only: keine Deaktivierungen.
    """
    by_value: dict[str, Any] = {}
    for row in existing_rows:
        key = getattr(row, value_attr)
        by_value[key] = row

    added = 0
    reactivated = 0
    for val in new_values:
        row = by_value.get(val)
        if row is None:
            on_insert(val)
            added += 1
        elif not row.is_active:
            row.is_active = True
            reactivated += 1

    removed = 0
    if not add_only:
        keep = set(new_values)
        for row in existing_rows:
            key = getattr(row, value_attr)
            if key not in keep and row.is_active:
                row.is_active = False
                removed += 1

    return {
        "added": added,
        "reactivated": reactivated,
        "removed": removed,
        "total": len(new_values),
    }
