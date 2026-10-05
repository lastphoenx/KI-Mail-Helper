"""BODYSTRUCTURE attachment detection — IMAPClient parse_fetch_response + Regressions."""

from imapclient.response_parser import parse_fetch_response

from src.services.folder_audit_service import FolderAuditService


def _bodystructure(uid: int, inner: str):
    """Parse synthetic FETCH line like the server/IMAPClient would."""
    line = f"{uid} (UID {uid} RFC822.SIZE 100 BODYSTRUCTURE {inner})"
    parsed = parse_fetch_response([line.encode("ascii")], uid)
    return parsed[uid][b"BODYSTRUCTURE"]


def _extract(inner: str, uid: int = 42):
    bs = _bodystructure(uid, inner)
    return FolderAuditService._extract_attachment_info(bs)


def test_multipart_pdf_name_only():
    inner = (
        '(( "TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "7BIT" 120 4 )'
        ' ( "APPLICATION" "PDF" ("NAME" "Scan2024.pdf") NIL NIL "BASE64" 50000 NIL )'
        ' "MIXED" )'
    )
    state, names, _ = _extract(inner)
    assert state == "yes"
    assert names == ["Scan2024.pdf"]


def test_scan_to_email_inline_jpeg_in_mixed_not_related():
    """Echter Scan-Anhang: inline + Dateiname, aber ohne CID / nicht in related."""
    inner = (
        '(( "TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "7BIT" 80 2 )'
        ' ( "IMAGE" "JPEG" ("NAME" "scan001.jpg") NIL NIL "BASE64" 200000 NIL'
        '   ("INLINE" ("FILENAME" "scan001.jpg")) )'
        ' "MIXED" )'
    )
    state, names, _ = _extract(inner)
    assert state == "yes"
    assert "scan001.jpg" in names


def test_outlook_signature_related_inline_cid_not_attachment():
    inner = (
        '(( "TEXT" "HTML" ("CHARSET" "UTF-8") NIL NIL "7BIT" 900 20 )'
        ' ( "IMAGE" "PNG" ("NAME" "image001.png") "<logo@outlook>" NIL "BASE64" 4000 NIL'
        '   ("INLINE" ("FILENAME" "image001.png")) )'
        ' "RELATED" )'
    )
    state, names, summary = _extract(inner)
    assert state == "no"
    assert names == []
    assert "Bild" in summary


def test_newsletter_banner_related_inline_cid_not_attachment():
    inner = (
        '(( "TEXT" "HTML" ("CHARSET" "UTF-8") NIL NIL "7BIT" 500 10 )'
        ' ( "IMAGE" "JPEG" ("NAME" "banner.jpg") "<news-banner-1>" NIL "BASE64" 12000 NIL'
        '   ("INLINE" ("FILENAME" "banner.jpg")) )'
        ' "RELATED" )'
    )
    state, names, _ = _extract(inner)
    assert state == "no"
    assert names == []


def test_smime_p7s_not_attachment():
    inner = (
        '(( "TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "7BIT" 200 4 )'
        ' ( "APPLICATION" "PKCS7-SIGNATURE" ("NAME" "smime.p7s") NIL NIL "BASE64" 800 NIL'
        '   ("ATTACHMENT" ("FILENAME" "smime.p7s")) )'
        ' "SIGNED" )'
    )
    state, names, _ = _extract(inner)
    assert state == "no"
    assert names == []


def test_message_rfc822_counts_as_attachment():
    inner = (
        '(( "TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "7BIT" 100 2 )'
        ' ( "MESSAGE" "RFC822" NIL NIL NIL "7BIT" 5000 NIL )'
        ' "MIXED" )'
    )
    state, names, _ = _extract(inner)
    assert state == "yes"
    assert any("Weitergeleitet" in n or "message" in n for n in names)


def test_rfc2231_filename_decoded():
    assert FolderAuditService._decode_rfc2231_filename_value("utf-8''scan%20document.pdf") == "scan document.pdf"
    inner = (
        '(( "APPLICATION" "PDF" ("filename*" "utf-8\'\'scan%20document.pdf") NIL NIL "BASE64" 9000 NIL )'
        ' "MIXED" )'
    )
    state, names, _ = _extract(inner)
    assert state == "yes"
    assert names == ["scan document.pdf"]


def test_attachment_disposition_tail_scan():
    inner = (
        '( "APPLICATION" "OCTET-STREAM" ("NAME" "data.bin") NIL NIL "BASE64" 9000 NIL "abc123"'
        '   ("ATTACHMENT" ("FILENAME" "data.bin")) )'
    )
    state, names, _ = _extract(inner)
    assert state == "yes"
    assert names == ["data.bin"]


def test_inline_gif_related_tracking_not_attachment():
    inner = (
        '(( "TEXT" "HTML" ("CHARSET" "UTF-8") NIL NIL "7BIT" 400 8 )'
        ' ( "IMAGE" "GIF" NIL "<track@pixel>" NIL "BASE64" 200 NIL'
        '   ("INLINE" NIL) )'
        ' "RELATED" )'
    )
    state, names, _ = _extract(inner)
    assert state == "no"
    assert names == []


def test_text_calendar_not_attachment():
    inner = (
        '( "TEXT" "CALENDAR" ("CHARSET" "UTF-8" "METHOD" "REQUEST") NIL NIL "7BIT" 1200 NIL )'
    )
    state, names, _ = _extract(inner)
    assert state == "no"
    assert names == []


def test_imapclient_related_subtype_at_index_one():
    inner = (
        '(( "TEXT" "HTML" ("CHARSET" "UTF-8") NIL NIL "7BIT" 100 2 )'
        ' ( "IMAGE" "PNG" ("NAME" "logo.png") "<x@y>" NIL "BASE64" 500 NIL'
        '   ("INLINE" ("FILENAME" "logo.png")) )'
        ' "RELATED" )'
    )
    bs = _bodystructure(42, inner)
    assert isinstance(bs, (list, tuple))
    assert isinstance(bs[0], (list, tuple))
    subtype = bs[1]
    if isinstance(subtype, bytes):
        assert subtype.lower() == b"related"
    else:
        assert str(subtype).lower() == "related"
    state, names, _ = FolderAuditService._extract_attachment_info(bs)
    assert state == "no"
    assert names == []


def test_missing_bodystructure_is_unknown():
    state, names, _ = FolderAuditService._extract_attachment_info(None)
    assert state == "unknown"
    assert names == []


def test_attachment_blocks_cluster_unknown():
    from src.services.folder_audit_service import TrashEmailInfo, TrashCategory
    from datetime import datetime

    info = TrashEmailInfo(
        uid=1,
        subject="x",
        sender="a@b.ch",
        sender_name="",
        date=datetime(2026, 1, 1),
        has_attachments=False,
        attachment_state="unknown",
        flags=[],
        size=1,
        category=TrashCategory.SAFE,
    )
    assert FolderAuditService.attachment_blocks_cluster(info) is True
