"""HTTP helpers for reverse-proxy aware URL generation."""

from __future__ import annotations

import os

from flask import request


def external_request_scheme() -> str:
    """Scheme for OAuth redirect URIs and external URLs."""
    if os.getenv("BEHIND_REVERSE_PROXY", "false").lower() == "true":
        return "https"
    if request:
        return request.scheme
    return "http"
