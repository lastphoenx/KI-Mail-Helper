"""
SMTP Web Routes - Phase G/J Integration
API-Endpoints für Email-Versand

Diese Datei enthält die Flask-Routes für:
- Email-Versand (Antwort und neue Emails)
- SMTP-Verbindungstest
- Integration mit Reply-Draft-Generator
"""

# ============================================================================
# ERGÄNZUNG FÜR src/01_web_app.py
# ============================================================================

# === IMPORTS (am Anfang der Datei hinzufügen) ===

from src.19_smtp_sender import (
    SMTPSender,
    OutgoingEmail,
    EmailRecipient,
    EmailAttachment,
    SendResult,
    send_reply_to_email,
    send_new_email
)


# ============================================================================
# SMTP TEST ROUTE
# ============================================================================

@app.route('/api/account/<int:account_id>/test-smtp', methods=['POST'])
@login_required
def api_test_smtp(account_id):
    """
    Testet die SMTP-Verbindung eines Mail-Accounts.
    
    Returns:
        {
            "success": true,
            "message": "SMTP-Verbindung erfolgreich"
        }
    """
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            "success": False,
            "error": "Nicht authentifiziert"
        }), 401
    
    # Account laden und Berechtigung prüfen
    account = MailAccount.query.get(account_id)
    if not account or account.user_id != current_user.id:
        return jsonify({
            "success": False,
            "error": "Account nicht gefunden"
        }), 404
    
    # SMTP testen
    try:
        sender = SMTPSender(account, master_key)
        success, message = sender.test_connection()
        
        return jsonify({
            "success": success,
            "message": message
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# SEND REPLY ROUTE
# ============================================================================

@app.route('/api/email/<int:email_id>/send-reply', methods=['POST'])
@login_required
def api_send_reply(email_id):
    """
    Sendet eine Antwort auf eine Email.
    
    POST Body:
    {
        "reply_text": "Danke für Ihre Nachricht...",
        "reply_html": "<p>Danke für Ihre Nachricht...</p>",  // optional
        "include_quote": true,  // optional, default: true
        "cc": ["cc@example.com"],  // optional
        "attachments": [  // optional
            {
                "filename": "dokument.pdf",
                "content_base64": "...",
                "mime_type": "application/pdf"
            }
        ]
    }
    
    Returns:
    {
        "success": true,
        "message_id": "<abc123@example.com>",
        "saved_to_sent": true,
        "sent_folder": "Gesendet",
        "saved_to_db": true,
        "db_email_id": 123
    }
    """
    import base64
    
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            "success": False,
            "error": "Nicht authentifiziert"
        }), 401
    
    # Email laden
    raw_email = RawEmail.query.get(email_id)
    if not raw_email or raw_email.user_id != current_user.id:
        return jsonify({
            "success": False,
            "error": "Email nicht gefunden"
        }), 404
    
    # Mail-Account prüfen
    account = MailAccount.query.get(raw_email.mail_account_id)
    if not account:
        return jsonify({
            "success": False,
            "error": "Mail-Account nicht gefunden"
        }), 404
    
    # Request-Body parsen
    data = request.get_json() or {}
    
    reply_text = data.get('reply_text')
    if not reply_text:
        return jsonify({
            "success": False,
            "error": "reply_text ist erforderlich"
        }), 400
    
    reply_html = data.get('reply_html')
    include_quote = data.get('include_quote', True)
    
    # CC-Empfänger parsen
    cc_recipients = None
    if data.get('cc'):
        cc_recipients = [EmailRecipient.from_string(addr) for addr in data['cc']]
    
    # Anhänge parsen (Base64 → Bytes)
    attachments = None
    if data.get('attachments'):
        attachments = []
        for att in data['attachments']:
            try:
                content = base64.b64decode(att['content_base64'])
                attachments.append(EmailAttachment(
                    filename=att['filename'],
                    content=content,
                    mime_type=att.get('mime_type', 'application/octet-stream')
                ))
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": f"Ungültiger Anhang: {e}"
                }), 400
    
    # SMTP Sender erstellen und Antwort senden
    try:
        sender = SMTPSender(account, master_key)
        result = sender.send_reply(
            original_email=raw_email,
            reply_text=reply_text,
            reply_html=reply_html,
            include_quote=include_quote,
            cc=cc_recipients,
            attachments=attachments
        )
        
        if result.success:
            return jsonify({
                "success": True,
                "message_id": result.message_id,
                "saved_to_sent": result.saved_to_sent,
                "sent_folder": result.sent_folder,
                "imap_uid": result.imap_uid,
                "saved_to_db": result.saved_to_db,
                "db_email_id": result.db_email_id
            })
        else:
            return jsonify({
                "success": False,
                "error": result.error
            }), 500
            
    except Exception as e:
        logger.error(f"Send-Reply Fehler: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# SEND NEW EMAIL ROUTE
# ============================================================================

@app.route('/api/account/<int:account_id>/send', methods=['POST'])
@login_required
def api_send_email(account_id):
    """
    Sendet eine neue Email (nicht als Antwort).
    
    POST Body:
    {
        "to": ["empfaenger@example.com"],
        "cc": ["cc@example.com"],  // optional
        "bcc": ["bcc@example.com"],  // optional
        "subject": "Betreff",
        "body_text": "Hallo...",
        "body_html": "<p>Hallo...</p>",  // optional
        "attachments": [...]  // optional, wie bei send-reply
    }
    
    Returns:
    {
        "success": true,
        "message_id": "<abc123@example.com>",
        ...
    }
    """
    import base64
    
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            "success": False,
            "error": "Nicht authentifiziert"
        }), 401
    
    # Account laden
    account = MailAccount.query.get(account_id)
    if not account or account.user_id != current_user.id:
        return jsonify({
            "success": False,
            "error": "Account nicht gefunden"
        }), 404
    
    # Request-Body parsen
    data = request.get_json() or {}
    
    # Pflichtfelder validieren
    if not data.get('to'):
        return jsonify({
            "success": False,
            "error": "Mindestens ein Empfänger (to) erforderlich"
        }), 400
    
    if not data.get('subject'):
        return jsonify({
            "success": False,
            "error": "Betreff (subject) erforderlich"
        }), 400
    
    if not data.get('body_text'):
        return jsonify({
            "success": False,
            "error": "Nachrichtentext (body_text) erforderlich"
        }), 400
    
    # Empfänger parsen
    to_recipients = [EmailRecipient.from_string(addr) for addr in data['to']]
    cc_recipients = [EmailRecipient.from_string(addr) for addr in data.get('cc', [])]
    bcc_recipients = [EmailRecipient.from_string(addr) for addr in data.get('bcc', [])]
    
    # Anhänge parsen
    attachments = []
    if data.get('attachments'):
        for att in data['attachments']:
            try:
                content = base64.b64decode(att['content_base64'])
                attachments.append(EmailAttachment(
                    filename=att['filename'],
                    content=content,
                    mime_type=att.get('mime_type', 'application/octet-stream')
                ))
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": f"Ungültiger Anhang: {e}"
                }), 400
    
    # OutgoingEmail erstellen
    email = OutgoingEmail(
        to=to_recipients,
        cc=cc_recipients,
        bcc=bcc_recipients,
        subject=data['subject'],
        body_text=data['body_text'],
        body_html=data.get('body_html'),
        attachments=attachments
    )
    
    # Senden
    try:
        sender = SMTPSender(account, master_key)
        result = sender.send_email(email)
        
        if result.success:
            return jsonify({
                "success": True,
                "message_id": result.message_id,
                "saved_to_sent": result.saved_to_sent,
                "sent_folder": result.sent_folder,
                "imap_uid": result.imap_uid,
                "saved_to_db": result.saved_to_db,
                "db_email_id": result.db_email_id
            })
        else:
            return jsonify({
                "success": False,
                "error": result.error
            }), 500
            
    except Exception as e:
        logger.error(f"Send-Email Fehler: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# GENERATE + SEND REPLY (KOMBINIERT MIT DRAFT GENERATOR)
# ============================================================================

@app.route('/api/email/<int:email_id>/generate-and-send', methods=['POST'])
@login_required
def api_generate_and_send_reply(email_id):
    """
    Generiert einen KI-Entwurf UND sendet ihn direkt.
    
    POST Body:
    {
        "tone": "formal",
        "custom_instructions": "Termine vorschlagen",
        "include_quote": true,
        "send_immediately": true  // false = nur generieren, nicht senden
    }
    
    Returns:
    {
        "success": true,
        "draft_text": "...",  // Der generierte Text
        "sent": true,         // Wurde gesendet?
        "message_id": "...",  // Falls gesendet
        ...
    }
    """
    from src.17_reply_service import generate_reply_draft
    
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            "success": False,
            "error": "Nicht authentifiziert"
        }), 401
    
    # Email laden
    raw_email = RawEmail.query.get(email_id)
    if not raw_email or raw_email.user_id != current_user.id:
        return jsonify({
            "success": False,
            "error": "Email nicht gefunden"
        }), 404
    
    data = request.get_json() or {}
    tone = data.get('tone', 'formal')
    custom_instructions = data.get('custom_instructions')
    include_quote = data.get('include_quote', True)
    send_immediately = data.get('send_immediately', False)
    
    # 1. Draft generieren
    draft = generate_reply_draft(
        email_id=email_id,
        master_key=master_key,
        tone=tone,
        custom_instructions=custom_instructions
    )
    
    if not draft:
        return jsonify({
            "success": False,
            "error": "Draft-Generierung fehlgeschlagen"
        }), 500
    
    response = {
        "success": True,
        "draft_text": draft['draft_text'],
        "subject": draft['subject'],
        "recipient": draft['recipient'],
        "tone": draft['tone'],
        "generation_time_ms": draft['generation_time_ms'],
        "sent": False
    }
    
    # 2. Optional: Direkt senden
    if send_immediately:
        account = MailAccount.query.get(raw_email.mail_account_id)
        if not account:
            response["send_error"] = "Mail-Account nicht gefunden"
            return jsonify(response)
        
        sender = SMTPSender(account, master_key)
        result = sender.send_reply(
            original_email=raw_email,
            reply_text=draft['draft_text'],
            include_quote=include_quote
        )
        
        if result.success:
            response["sent"] = True
            response["message_id"] = result.message_id
            response["saved_to_sent"] = result.saved_to_sent
            response["saved_to_db"] = result.saved_to_db
        else:
            response["send_error"] = result.error
    
    return jsonify(response)


# ============================================================================
# SMTP STATUS ROUTE
# ============================================================================

@app.route('/api/account/<int:account_id>/smtp-status', methods=['GET'])
@login_required
def api_smtp_status(account_id):
    """
    Prüft ob SMTP für einen Account konfiguriert ist.
    
    Returns:
    {
        "configured": true,
        "server": "smtp.example.com",
        "port": 587,
        "encryption": "STARTTLS"
    }
    """
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            "success": False,
            "error": "Nicht authentifiziert"
        }), 401
    
    account = MailAccount.query.get(account_id)
    if not account or account.user_id != current_user.id:
        return jsonify({
            "success": False,
            "error": "Account nicht gefunden"
        }), 404
    
    # Prüfen ob SMTP konfiguriert
    has_smtp = bool(
        account.encrypted_smtp_server and 
        (account.encrypted_smtp_password or account.encrypted_imap_password)
    )
    
    if has_smtp:
        sender = SMTPSender(account, master_key)
        is_valid, error = sender.validate_configuration()
        
        return jsonify({
            "success": True,
            "configured": is_valid,
            "server": sender.credentials.get("smtp_server") if is_valid else None,
            "port": account.smtp_port,
            "encryption": account.smtp_encryption,
            "error": error if not is_valid else None
        })
    else:
        return jsonify({
            "success": True,
            "configured": False,
            "error": "SMTP nicht konfiguriert"
        })
