"""
Diesen Code in src/01_web_app.py VOR @app.errorhandler(404) einfügen:
"""

@app.route("/mail-account/<int:account_id>/fetch", methods=["POST"])
@login_required
def fetch_mails(account_id):
    """Holt Mails für einen Account ab"""
    import importlib
    mail_fetcher = importlib.import_module('.06_mail_fetcher', 'src')
    
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))
        
        account = db.query(models.MailAccount).filter_by(
            id=account_id,
            user_id=user.id
        ).first()
        
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404
        
        master_key = session.get('master_key')
        if not master_key:
            return jsonify({"error": "Master-Key nicht gespeichert"}), 401
        
        imap_password = encryption.CredentialManager.decrypt_imap_password(
            account.encrypted_imap_password,
            master_key
        )
        
        fetcher = mail_fetcher.MailFetcher(
            server=account.imap_server,
            username=account.imap_username,
            password=imap_password,
            port=account.imap_port
        )
        
        fetcher.connect()
        raw_emails = fetcher.fetch_new_emails(limit=50)
        fetcher.disconnect()
        
        if not raw_emails:
            return jsonify({"status": "ok", "message": "Keine neuen Mails"})
        
        logger.info(f"📧 {len(raw_emails)} Mails abgerufen von {account.name}")
        return jsonify({"status": "ok", "count": len(raw_emails)})
    
    except Exception as e:
        logger.error(f"Fehler beim Mail-Abruf: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        db.close()
