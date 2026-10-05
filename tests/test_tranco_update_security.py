"""Tranco-Download-Sicherheit und Store-Reload."""

import sqlite3

import requests

from src.services.tranco_update import (
    TrancoStepHttpError,
    _allowed_tranco_url,
    _failure_from_exception,
    _resolve_tranco_redirect,
    resolve_tranco_download_url,
    TRANCO_DAILY_ZIP_URL,
)


def test_allowed_tranco_url_rejects_substring_traps():
    assert _allowed_tranco_url("https://tranco-list.eu/download/X/1000000")
    assert not _allowed_tranco_url("https://tranco-list.eu.evil.example/x")
    assert not _allowed_tranco_url("https://evil.example/tranco-list.eu/x")
    assert not _allowed_tranco_url("http://tranco-list.eu/x")
    assert not _allowed_tranco_url("http://evil.example/?h=tranco-list.eu")


def test_failure_from_sqlite_unable_to_open():
    exc = sqlite3.OperationalError("unable to open database file")
    out = _failure_from_exception(exc)
    assert out["ok"] is False
    assert "mailhelper" in out["hint"]


def test_failure_from_permission_error():
    out = _failure_from_exception(PermissionError(13, "Permission denied"))
    assert "Schreibrechte" in out["error"]


def test_failure_from_value_error_download_size():
    out = _failure_from_exception(ValueError("Tranco download exceeds 999 bytes"))
    assert "Größenlimit" in out["error"]


def test_failure_from_requests():
    out = _failure_from_exception(requests.Timeout("slow"))
    assert "Netzwerkfehler" in out["error"]


def test_failure_from_http_error():
    out = _failure_from_exception(requests.HTTPError(response=requests.Response()))
    assert "HTTP-Fehlerstatus" in out["error"]


def test_failure_from_tranco_step_http():
    out = _failure_from_exception(TrancoStepHttpError("Listen-ID", 404))
    assert out["error"] == "Tranco Listen-ID: HTTP 404"


def test_resolve_tranco_list_id_zip_falls_back_to_yesterday(monkeypatch):
    from src.services import tranco_update

    calls: list = []

    def fake_fetch(*, day=None):
        calls.append(day.date() if day else None)
        if len(calls) == 1:
            raise ValueError("daily_list_id invalid")
        return "YESTERDAY"

    monkeypatch.delenv("TRANCO_LIST_ID", raising=False)
    monkeypatch.setattr(tranco_update, "fetch_daily_tranco_list_id", fake_fetch)
    lid = tranco_update.resolve_tranco_list_id(align_with_daily_zip=True)
    assert lid == "YESTERDAY"
    assert len(calls) == 2


def test_failure_from_empty_download():
    out = _failure_from_exception(ValueError("Tranco download empty body"))
    assert "leer" in out["error"].lower()


def test_resolve_tranco_redirect_relative():
    nxt = _resolve_tranco_redirect(
        TRANCO_DAILY_ZIP_URL,
        "/download/daily/top-1m.csv.zip",
    )
    assert nxt == f"https://tranco-list.eu/download/daily/top-1m.csv.zip"


def test_default_download_url_is_daily_zip(monkeypatch):
    monkeypatch.delenv("TRANCO_DOWNLOAD_URL", raising=False)
    monkeypatch.delenv("TRANCO_DOWNLOAD_MODE", raising=False)
    assert resolve_tranco_download_url("Y83KG") == TRANCO_DAILY_ZIP_URL
