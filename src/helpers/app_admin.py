"""App-Administrator (kein DB-Rollenmodell — bis is_admin existiert)."""

from __future__ import annotations

import os


def user_is_app_admin(user) -> bool:
    if user is None:
        return False
    raw = os.getenv("APP_ADMIN_USERNAMES", "").strip()
    if raw:
        allowed = {n.strip().lower() for n in raw.split(",") if n.strip()}
        return (getattr(user, "username", "") or "").lower() in allowed
    return int(getattr(user, "id", 0) or 0) == 1
