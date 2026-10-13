"""Ordner-Audit UI rendert (Jinja-Makros)."""


def test_folder_audit_html_compiles(app):
    with app.test_request_context():
        from flask import render_template

        html = render_template("folder_audit.html", accounts=[])
        assert "Was will ich?" in html
        assert "brand-official-domains/add" in html or "brand-domain" in html
        assert 'id="config-marken-domains"' in html
        assert "auditLocationWithHash" in html
        assert "applyFolderAuditHashFromLocation" in html
