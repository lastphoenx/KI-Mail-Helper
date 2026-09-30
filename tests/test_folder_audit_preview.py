"""On-demand Textpreview für Folder-Audit (kein Body beim Scan)."""
from src.services.folder_audit_service import (
    FolderAuditService,
    TrashEmailInfo,
    preview_body_to_text,
)


def test_preview_strips_html_and_scripts():
    raw = b"""<html><head><style>p{color:red}</style></head>
    <body><script>alert(1)</script><p>Ciao Pagamenti</p><br>IBAN: IT00</body></html>"""
    text = preview_body_to_text(raw)
    assert "Ciao Pagamenti" in text
    assert "IBAN: IT00" in text
    assert "alert(1)" not in text
    assert "<script" not in text.lower()
    assert "color:red" not in text


def test_preview_truncates():
    text = preview_body_to_text("x" * 50, max_chars=20)
    assert text.startswith("x" * 20)
    assert text.endswith("…")
    assert len(text) < 50


def test_preview_unescapes_entities():
    assert "A & B" in preview_body_to_text("A &amp; B")


def test_to_dict_includes_header_fields_for_details_panel():
    info = TrashEmailInfo(
        uid=12,
        subject="RE:Pagamenti",
        sender="AssistenzaClientiInternetBanking@cagroupsolutions.it",
        sender_name="Assistenza Clienti",
        date=None,
        has_attachments=False,
        flags=[],
        size=4321,
        reply_to="noreply@cagroupsolutions.it",
        auth_results="dkim=fail; spf=pass",
        x_mailer="Unknown",
        server_spam_flag=True,
        provider_junk_score=10,
        folder="INBOX/Fano_Italien",
        to_header="undisclosed-recipients:;",
    )
    d = info.to_dict()
    assert d["reply_to"] == "noreply@cagroupsolutions.it"
    assert "dkim=fail" in d["auth_results"]
    assert d["server_spam_flag"] is True
    assert d["provider_junk_score"] == 10
    assert d["folder"] == "INBOX/Fano_Italien"
    assert d["to_header"] == "undisclosed-recipients:;"


def test_peek_text_rejects_all_folders_sentinel():
    class Dummy:
        connection = object()

    try:
        FolderAuditService.peek_text(Dummy(), "__ALL__", 1)
        assert False, "expected ValueError"
    except ValueError:
        pass
