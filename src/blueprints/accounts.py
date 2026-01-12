# src/blueprints/accounts.py
"""Accounts Blueprint - Settings, Mail-Accounts, Fetch-Config.

Routes (22 total):
    1. /reply-styles (GET) - reply_styles_page
    2. /settings (GET) - settings
    3. /mail-fetch-config (GET) - mail_fetch_config
    4. /whitelist (GET) - whitelist
    5. /ki-prio (GET) - ki_prio
    6. /settings/fetch-config (POST) - save_fetch_config
    7. /account/<id>/fetch-filters (GET) - get_account_fetch_filters
    8. /settings/ai (POST) - save_ai_preferences
    9. /settings/password (GET,POST) - change_password
    10. /settings/mail-account/select-type (GET) - select_account_type
    11. /settings/mail-account/google-setup (GET,POST) - google_oauth_setup
    12. /settings/mail-account/google/callback (GET) - google_oauth_callback
    13. /settings/mail-account/add (GET,POST) - add_mail_account
    14. /settings/mail-account/<id>/edit (GET,POST) - edit_mail_account
    15. /settings/mail-account/<id>/delete (POST) - delete_mail_account
    16. /imap-diagnostics (GET) - imap_diagnostics
    17. /mail-account/<id>/fetch (POST) - fetch_mails
    18. /mail-account/<id>/purge (POST) - purge_mail_account
    19. /jobs/<job_id> (GET) - job_status
    20. /account/<id>/mail-count (GET) - get_account_mail_count
    21. /account/<id>/folders (GET) - get_account_folders
    22. /whitelist-imap-setup (GET) - whitelist_imap_setup_page

Extracted from 01_web_app.py lines: 2392-2720, 6322-6490, 6583-7520, 7763-8020, 8985-9050
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session, flash, g
from flask_login import login_required, logout_user, current_user
from datetime import datetime, UTC
import json
import time
import importlib
import logging

from src.helpers import get_db_session, get_current_user_model

accounts_bp = Blueprint("accounts", __name__)
logger = logging.getLogger(__name__)

# Lazy imports
_models = None
_encryption = None
_auth = None
_google_oauth = None
_password_validator = None
_mail_fetcher_mod = None
_job_queue = None

# Caches für mail-count
_mail_count_cache = {}
_mail_count_cache_time = {}
MAIL_COUNT_CACHE_TTL = 30


def _get_models():
    global _models
    if _models is None:
        _models = importlib.import_module(".02_models", "src")
    return _models


def _get_encryption():
    global _encryption
    if _encryption is None:
        _encryption = importlib.import_module(".08_encryption", "src")
    return _encryption


def _get_auth():
    global _auth
    if _auth is None:
        _auth = importlib.import_module(".07_auth", "src")
    return _auth


def _get_google_oauth():
    global _google_oauth
    if _google_oauth is None:
        _google_oauth = importlib.import_module(".10_google_oauth", "src")
    return _google_oauth


def _get_password_validator():
    global _password_validator
    if _password_validator is None:
        _password_validator = importlib.import_module(".09_password_validator", "src")
    return _password_validator


def _get_mail_fetcher_mod():
    global _mail_fetcher_mod
    if _mail_fetcher_mod is None:
        _mail_fetcher_mod = importlib.import_module(".04_mail_fetcher", "src")
    return _mail_fetcher_mod


def _get_job_queue():
    global _job_queue
    if _job_queue is None:
        job_mod = importlib.import_module(".14_background_jobs", "src")
        _job_queue = job_mod.job_queue
    return _job_queue


# =============================================================================
# Route 1: /reply-styles (Zeile 2392)
# =============================================================================
@accounts_bp.route("/reply-styles")
@login_required
def reply_styles_page():
    """Seite für Antwort-Stil-Einstellungen"""
    return render_template("reply_styles.html")


# =============================================================================
# Route 2: /settings (Zeile 2399-2486)
# =============================================================================
@accounts_bp.route("/settings")
@login_required
def settings():
    """Settings-Seite: Mail-Accounts, 2FA, AI-Provider (Base + Optimize), etc."""
    models = _get_models()
    encryption = _get_encryption()
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("auth.login"))

        mail_accounts = db.query(models.MailAccount).filter_by(user_id=user.id).all()

        master_key = session.get("master_key")
        if master_key:
            for account in mail_accounts:
                try:
                    if account.encrypted_imap_server:
                        account.imap_server = encryption.CredentialManager.decrypt_server(
                            account.encrypted_imap_server, master_key
                        )
                    if account.encrypted_imap_username:
                        account.imap_username = encryption.CredentialManager.decrypt_email_address(
                            account.encrypted_imap_username, master_key
                        )
                    if account.encrypted_smtp_server:
                        account.smtp_server = encryption.CredentialManager.decrypt_server(
                            account.encrypted_smtp_server, master_key
                        )
                    if account.encrypted_smtp_username:
                        account.smtp_username = encryption.CredentialManager.decrypt_email_address(
                            account.encrypted_smtp_username, master_key
                        )
                except Exception as e:
                    logger.warning(f"Konnte Account {account.id} nicht entschlüsseln: {e}")
                    account.imap_server = "***verschlüsselt***"
                    account.imap_username = "***verschlüsselt***"

        selected_provider_embedding = (user.preferred_embedding_provider or "ollama").lower()
        selected_model_embedding = user.preferred_embedding_model or "all-minilm:22m"
        selected_provider_base = (user.preferred_ai_provider or "ollama").lower()
        selected_model_base = user.preferred_ai_model or "llama3.2:1b"
        selected_provider_optimize = (user.preferred_ai_provider_optimize or "ollama").lower()
        selected_model_optimize = user.preferred_ai_model_optimize or "llama3.2:3b"

        user_prefs = {
            'mails_per_folder': getattr(user, 'fetch_mails_per_folder', 100),
            'max_total_mails': getattr(user, 'fetch_max_total', 0),
            'use_delta_sync': getattr(user, 'fetch_use_delta_sync', True),
        }

        return render_template(
            "settings.html",
            user=user,
            mail_accounts=mail_accounts,
            totp_enabled=user.totp_enabled,
            ai_selected_provider_embedding=selected_provider_embedding,
            ai_selected_model_embedding=selected_model_embedding,
            ai_selected_provider_base=selected_provider_base,
            ai_selected_model_base=selected_model_base,
            ai_selected_provider_optimize=selected_provider_optimize,
            ai_selected_model_optimize=selected_model_optimize,
            user_prefs=user_prefs,
            now=datetime.now,
        )


# =============================================================================
# Route 3: /mail-fetch-config (Zeile 2488-2524)
# =============================================================================
@accounts_bp.route("/mail-fetch-config")
@login_required
def mail_fetch_config():
    """Mail Fetch Configuration: AI Analysis & Anonymization Settings"""
    models = _get_models()
    encryption = _get_encryption()
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("auth.login"))
        
        mail_accounts = db.query(models.MailAccount).filter_by(user_id=user.id).all()
        
        master_key = session.get("master_key")
        if master_key and mail_accounts:
            for account in mail_accounts:
                if account.auth_type == "imap" and account.encrypted_imap_username:
                    try:
                        account.decrypted_imap_username = encryption.EmailDataManager.decrypt_email_sender(
                            account.encrypted_imap_username, master_key
                        )
                    except Exception as e:
                        logger.warning(f"Fehler beim Entschlüsseln der Account-Email: {e}")
                        account.decrypted_imap_username = None
        
        return render_template("mail_fetch_config.html", user=user, mail_accounts=mail_accounts)


# =============================================================================
# Route 4: /whitelist (Zeile 2526-2562)
# =============================================================================
@accounts_bp.route("/whitelist")
@login_required
def whitelist():
    """Whitelist/Trusted Senders Management Page"""
    models = _get_models()
    encryption = _get_encryption()
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("auth.login"))
        
        mail_accounts = db.query(models.MailAccount).filter_by(user_id=user.id).all()
        
        master_key = session.get("master_key")
        if master_key and mail_accounts:
            for account in mail_accounts:
                if account.auth_type == "imap" and account.encrypted_imap_username:
                    try:
                        account.decrypted_imap_username = encryption.EmailDataManager.decrypt_email_sender(
                            account.encrypted_imap_username, master_key
                        )
                    except Exception as e:
                        logger.warning(f"Fehler beim Entschlüsseln der Account-Email: {e}")
                        account.decrypted_imap_username = None
        
        return render_template("whitelist.html", user=user, mail_accounts=mail_accounts)


# =============================================================================
# Route 5: /ki-prio (Zeile 2564-2569)
# =============================================================================
@accounts_bp.route("/ki-prio")
@login_required
def ki_prio():
    """KI-gestützte E-Mail Priorisierung: Konfiguration für spaCy Hybrid Pipeline"""
    return render_template("phase_y_config.html", csp_nonce=g.get("csp_nonce", ""))


# =============================================================================
# Route 6: /settings/fetch-config (Zeile 2571-2665)
# =============================================================================
@accounts_bp.route("/settings/fetch-config", methods=["POST"])
@login_required
def save_fetch_config():
    """Speichert Fetch-Präferenzen für einen spezifischen Account"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return redirect(url_for("auth.login"))

            account_id = request.form.get('account_id')
            if not account_id:
                flash("❌ Bitte Account auswählen", "error")
                return redirect(url_for("accounts.settings"))
            
            # Validate account_id is numeric
            try:
                account_id = int(account_id)
            except (ValueError, TypeError):
                flash("❌ Ungültige Account-ID", "error")
                return redirect(url_for("accounts.settings"))
            
            account = db.query(models.MailAccount).filter(
                models.MailAccount.id == account_id,
                models.MailAccount.user_id == user.id
            ).first()
            
            if not account:
                flash("❌ Account nicht gefunden", "error")
                return redirect(url_for("accounts.settings"))

            # Parse and validate inputs
            try:
                mails_per_folder = int(request.form.get('mails_per_folder', 100))
                max_total_mails = int(request.form.get('max_total_mails', 0))
            except (ValueError, TypeError):
                flash("❌ Ungültige Zahlenangabe", "error")
                return redirect(url_for("accounts.settings"))
            
            use_delta_sync = request.form.get('use_delta_sync') == 'on'
            since_date_str = request.form.get('since_date', '').strip()
            unseen_only = request.form.get('unseen_only') == 'on'
            include_folders = request.form.getlist('include_folders')
            exclude_folders = request.form.getlist('exclude_folders')

            if mails_per_folder < 10 or mails_per_folder > 1000:
                flash("❌ Mails pro Ordner muss zwischen 10 und 1000 liegen", "error")
                return redirect(url_for("accounts.settings"))
            
            if max_total_mails < 0 or max_total_mails > 10000:
                flash("❌ Max. Gesamt muss zwischen 0 und 10000 liegen", "error")
                return redirect(url_for("accounts.settings"))

            since_date = None
            if since_date_str:
                try:
                    since_date = datetime.strptime(since_date_str, '%Y-%m-%d').date()
                except ValueError:
                    flash("❌ Ungültiges Datum-Format (YYYY-MM-DD erwartet)", "error")
                    return redirect(url_for("accounts.settings"))

            user.fetch_mails_per_folder = mails_per_folder
            user.fetch_max_total = max_total_mails
            user.fetch_use_delta_sync = use_delta_sync
            
            account.fetch_since_date = since_date
            account.fetch_unseen_only = unseen_only
            account.fetch_include_folders = json.dumps(include_folders) if include_folders else None
            account.fetch_exclude_folders = json.dumps(exclude_folders) if exclude_folders else None
            
            try:
                db.commit()
                flash(f"✅ Filter für '{account.name}' gespeichert", "success")
            except Exception as e:
                db.rollback()
                logger.error(f"save_fetch_config: Commit-Fehler: {type(e).__name__}: {e}")
                flash("❌ Fehler beim Speichern der Konfiguration", "error")
            
            return redirect(url_for("accounts.settings") + f"#fetch_config_account_{account_id}")
    except Exception as e:
        logger.error(f"save_fetch_config: Fehler: {type(e).__name__}: {e}")
        flash("❌ Unerwarteter Fehler beim Speichern", "error")
        return redirect(url_for("accounts.settings"))


# =============================================================================
# Route 7: /account/<id>/fetch-filters (Zeile 2667-2720)
# =============================================================================
@accounts_bp.route("/account/<int:account_id>/fetch-filters", methods=["GET"])
@login_required
def get_account_fetch_filters(account_id):
    """Lade die Fetch-Filter für einen bestimmten Account"""
    models = _get_models()
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        account = db.query(models.MailAccount).filter(
            models.MailAccount.id == account_id,
            models.MailAccount.user_id == user.id
        ).first()
        
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404
        
        include_folders = []
        exclude_folders = []
        
        if account.fetch_include_folders:
            try:
                include_folders = json.loads(account.fetch_include_folders)
            except:
                pass
        
        if account.fetch_exclude_folders:
            try:
                exclude_folders = json.loads(account.fetch_exclude_folders)
            except:
                pass
        
        return jsonify({
            "account_id": account_id,
            "account_name": account.name,
            "since_date": account.fetch_since_date.strftime('%Y-%m-%d') if account.fetch_since_date else None,
            "unseen_only": account.fetch_unseen_only or False,
            "include_folders": include_folders,
            "exclude_folders": exclude_folders,
            "has_filters": bool(account.fetch_since_date or account.fetch_unseen_only or include_folders or exclude_folders)
        })


# =============================================================================
# Route 8: /settings/ai (Zeile 6322-6378)
# =============================================================================
@accounts_bp.route("/settings/ai", methods=["POST"])
@login_required
def save_ai_preferences():
    """Speichert KI-Provider- und Modellpräferenzen für Embedding + Base + Optimize Pass."""
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return redirect(url_for("auth.login"))

            provider_embedding = (request.form.get("ai_provider_embedding") or "ollama").lower().strip()
            model_embedding = (request.form.get("ai_model_embedding") or "").strip()
            provider_base = (request.form.get("ai_provider_base") or "ollama").lower().strip()
            model_base = (request.form.get("ai_model_base") or "").strip()
            provider_optimize = (request.form.get("ai_provider_optimize") or "ollama").lower().strip()
            model_optimize = (request.form.get("ai_model_optimize") or "").strip()

            # Input validation - max lengths
            if len(provider_embedding) > 50 or len(provider_base) > 50 or len(provider_optimize) > 50:
                flash("Provider-Name zu lang (max. 50 Zeichen)", "danger")
                return redirect(url_for("accounts.settings"))
            
            if len(model_embedding) > 100 or len(model_base) > 100 or len(model_optimize) > 100:
                flash("Model-Name zu lang (max. 100 Zeichen)", "danger")
                return redirect(url_for("accounts.settings"))

            if not model_embedding:
                flash("Embedding-Model ist erforderlich!", "danger")
                return redirect(url_for("accounts.settings"))
            
            if not model_base:
                flash("Base-Model ist erforderlich!", "danger")
                return redirect(url_for("accounts.settings"))
                
            if not model_optimize:
                flash("Optimize-Model ist erforderlich!", "danger")
                return redirect(url_for("accounts.settings"))

            user.preferred_embedding_provider = provider_embedding
            user.preferred_embedding_model = model_embedding
            user.preferred_ai_provider = provider_base
            user.preferred_ai_model = model_base
            user.preferred_ai_provider_optimize = provider_optimize
            user.preferred_ai_model_optimize = model_optimize
            
            try:
                db.commit()
                flash("✅ KI-Präferenzen gespeichert (Embedding + Base + Optimize).", "success")
            except Exception as e:
                db.rollback()
                logger.error(f"save_ai_preferences: Commit-Fehler: {type(e).__name__}: {e}")
                flash("❌ Speichern fehlgeschlagen", "danger")
            
            return redirect(url_for("accounts.settings"))
    except Exception as e:
        logger.error(f"save_ai_preferences: Fehler: {type(e).__name__}: {e}")
        flash("❌ Unerwarteter Fehler", "danger")
        return redirect(url_for("accounts.settings"))


# =============================================================================
# Route 9: /settings/password (Zeile 6380-6470)
# =============================================================================
@accounts_bp.route("/settings/password", methods=["GET", "POST"])
@login_required
def change_password():
    """Passwort-Änderung mit KEK-Neuableitung"""
    encryption = _get_encryption()
    auth = _get_auth()
    password_validator = _get_password_validator()
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("auth.login"))

        if request.method == "POST":
            old_password = request.form.get("old_password", "").strip()
            new_password = request.form.get("new_password", "").strip()
            new_password_confirm = request.form.get("new_password_confirm", "").strip()

            if not all([old_password, new_password, new_password_confirm]):
                flash("Alle Felder sind erforderlich", "danger")
                return render_template("change_password.html")

            if new_password != new_password_confirm:
                flash("Neue Passwörter stimmen nicht überein", "danger")
                return render_template("change_password.html")

            if not user.check_password(old_password):
                flash("Altes Passwort ist falsch", "danger")
                return render_template("change_password.html")

            is_valid, error_msg = password_validator.PasswordValidator.validate(new_password)
            if not is_valid:
                flash(error_msg, "danger")
                return render_template("change_password.html")

            try:
                old_dek = auth.MasterKeyManager.decrypt_dek_from_password(user, old_password)
                if not old_dek:
                    flash("DEK-Entschlüsselung fehlgeschlagen", "danger")
                    return render_template("change_password.html")

                new_salt = encryption.EncryptionManager.generate_salt()
                new_kek = encryption.EncryptionManager.generate_master_key(new_password, new_salt)
                new_encrypted_dek = encryption.EncryptionManager.encrypt_dek(old_dek, new_kek)

                user.salt = new_salt
                user.encrypted_dek = new_encrypted_dek
                user.set_password(new_password)
                db.commit()

                logger.info(f"✅ Passwort geändert für User {user.id}")

                session.clear()
                logout_user()

                flash("Passwort erfolgreich geändert! Bitte neu anmelden.", "success")
                return redirect(url_for("auth.login"))

            except Exception as e:
                logger.error(f"❌ Fehler bei Passwort-Änderung: {type(e).__name__}")
                flash("Passwort-Änderung fehlgeschlagen.", "danger")
                return render_template("change_password.html")

        return render_template("change_password.html")


# =============================================================================
# Route 10: /settings/mail-account/select-type (Zeile 6583-6588)
# =============================================================================
@accounts_bp.route("/settings/mail-account/select-type", methods=["GET"])
@login_required
def select_account_type():
    """Wählt Konto-Typ: Google OAuth oder Manuell"""
    return render_template("select_account_type.html")


# =============================================================================
# Route 11: /settings/mail-account/google-setup (Zeile 6590-6637)
# =============================================================================
@accounts_bp.route("/settings/mail-account/google-setup", methods=["GET", "POST"])
@login_required
def google_oauth_setup():
    """Google OAuth Setup: Sammelt Client ID/Secret und startet OAuth Flow"""
    auth = _get_auth()
    google_oauth = _get_google_oauth()
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("auth.login"))

        if request.method == "POST":
            client_id = request.form.get("client_id", "").strip()
            client_secret = request.form.get("client_secret", "").strip()

            if not client_id or not client_secret:
                return render_template(
                    "google_oauth_setup.html",
                    step=1,
                    error="Client-ID und Client-Secret sind erforderlich",
                ), 400

            session["google_oauth_client_id"] = client_id
            session["google_oauth_client_secret"] = client_secret
            session["google_oauth_state"] = auth.AuthManager.generate_totp_secret()[:16]

            redirect_uri = url_for("accounts.google_oauth_callback", _external=True, _scheme="http")

            auth_url = google_oauth.GoogleOAuthManager.get_auth_url(
                client_id=client_id,
                redirect_uri=redirect_uri,
                state=session["google_oauth_state"],
            )

            return render_template("google_oauth_setup.html", step=2, google_auth_url=auth_url)

        return render_template("google_oauth_setup.html", step=1)


# =============================================================================
# Route 12: /settings/mail-account/google/callback (Zeile 6639-6807)
# =============================================================================
@accounts_bp.route("/settings/mail-account/google/callback", methods=["GET"])
@login_required
def google_oauth_callback():
    """Google OAuth Callback: Tauscht Auth Code gegen Token"""
    from sqlalchemy.exc import IntegrityError
    
    models = _get_models()
    encryption = _get_encryption()
    google_oauth = _get_google_oauth()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return redirect(url_for("auth.login"))

            code = request.args.get("code")
            state = request.args.get("state")
            error = request.args.get("error")

            if error:
                logger.warning(f"google_oauth_callback: OAuth error: {error}")
                flash(f"Google OAuth Fehler: {error}", "danger")
                return redirect(url_for("accounts.settings"))

            if not code or not state:
                logger.warning("google_oauth_callback: Missing code or state")
                flash("Ungültige OAuth-Antwort", "danger")
                return redirect(url_for("accounts.settings"))

            if state != session.get("google_oauth_state"):
                logger.warning(f"google_oauth_callback: State mismatch for user {user.id}")
                flash("OAuth State mismatch - möglicher CSRF-Angriff", "danger")
                return redirect(url_for("accounts.settings"))

            client_id = session.get("google_oauth_client_id")
            client_secret = session.get("google_oauth_client_secret")
            
            if not client_id or not client_secret:
                logger.warning("google_oauth_callback: Missing client credentials in session")
                flash("Session-Daten fehlen. Bitte erneut versuchen.", "danger")
                return redirect(url_for("accounts.google_oauth_setup"))
            
            redirect_uri = url_for("accounts.google_oauth_callback", _external=True, _scheme="http")

            try:
                tokens = google_oauth.GoogleOAuthManager.exchange_code(
                    code=code,
                    client_id=client_id,
                    client_secret=client_secret,
                    redirect_uri=redirect_uri,
                )

                access_token = tokens.get("access_token")
                refresh_token = tokens.get("refresh_token")
                expires_in = tokens.get("expires_in", 3600)

                if not access_token:
                    logger.error("google_oauth_callback: No access token received")
                    flash("Kein Access-Token von Google erhalten", "danger")
                    return redirect(url_for("accounts.settings"))

                user_info = google_oauth.GoogleOAuthManager.get_user_info(access_token)
                email = user_info.get("email")

                if not email:
                    logger.warning("google_oauth_callback: No email in user info")
                    flash("Google-Konto hat keine E-Mail-Adresse", "danger")
                    return redirect(url_for("accounts.settings"))

                master_key = session.get("master_key")
                if not master_key:
                    flash("Session abgelaufen", "danger")
                    return redirect(url_for("auth.login"))

                account = models.MailAccount(
                    user_id=user.id,
                    name=email,
                    auth_type="oauth",
                    encrypted_imap_server=encryption.CredentialManager.encrypt_server("imap.gmail.com", master_key),
                    imap_port=993,
                    encrypted_smtp_server=encryption.CredentialManager.encrypt_server("smtp.gmail.com", master_key),
                    smtp_port=587,
                    encrypted_imap_username=encryption.CredentialManager.encrypt_email_address(email, master_key),
                    encrypted_smtp_username=encryption.CredentialManager.encrypt_email_address(email, master_key),
                    encrypted_oauth_access_token=encryption.CredentialManager.encrypt_imap_password(access_token, master_key),
                    encrypted_oauth_refresh_token=encryption.CredentialManager.encrypt_imap_password(refresh_token or "", master_key),
                    encrypted_oauth_client_id=encryption.CredentialManager.encrypt_imap_password(client_id, master_key),
                    encrypted_oauth_client_secret=encryption.CredentialManager.encrypt_imap_password(client_secret, master_key),
                    oauth_token_expires_at=datetime.now(UTC) + __import__('datetime').timedelta(seconds=expires_in),
                )
                db.add(account)
                
                try:
                    db.commit()
                    logger.info(f"google_oauth_callback: Account '{email}' created for user {user.id}")
                except IntegrityError:
                    db.rollback()
                    logger.warning(f"google_oauth_callback: Duplicate email '{email}' for user {user.id}")
                    flash(f"Email '{email}' ist bereits mit einem Account verbunden", "danger")
                    return redirect(url_for("accounts.settings"))
                except Exception as e:
                    db.rollback()
                    logger.error(f"google_oauth_callback: Commit-Fehler: {type(e).__name__}: {e}")
                    flash("❌ Fehler beim Speichern des Accounts", "danger")
                    return redirect(url_for("accounts.settings"))

                # Cleanup session
                session.pop("google_oauth_client_id", None)
                session.pop("google_oauth_client_secret", None)
                session.pop("google_oauth_state", None)

                flash(f"✅ Google-Konto '{email}' erfolgreich verbunden!", "success")
                return redirect(url_for("accounts.settings"))

            except Exception as e:
                logger.error(f"google_oauth_callback: Token exchange error: {type(e).__name__}: {e}")
                flash(f"Fehler beim Verbinden: {str(e)}", "danger")
                return redirect(url_for("accounts.settings"))
    except Exception as e:
        logger.error(f"google_oauth_callback: Unerwarteter Fehler: {type(e).__name__}: {e}")
        flash("❌ Unerwarteter Fehler beim OAuth-Callback", "danger")
        return redirect(url_for("accounts.settings"))


# =============================================================================
# Hilfsfunktion: ensure_master_key_in_session (aus 01_web_app.py)
# =============================================================================
def ensure_master_key_in_session():
    """Stellt sicher, dass der Master-Key in der Session ist."""
    if "master_key" in session:
        return True
    return False


# =============================================================================
# Hilfsfunktion: initialize_phase_y_config (Lazy Import)
# =============================================================================
def _initialize_phase_y_config(db, user_id, mail_account_id, email_domain):
    """Wrapper für Phase Y Config Initialisierung."""
    try:
        # Phase Y Config ist optional - bei Fehler ignorieren
        models = _get_models()
        config = db.query(models.PhaseYConfig).filter_by(
            user_id=user_id, mail_account_id=mail_account_id
        ).first()
        if not config:
            config = models.PhaseYConfig(
                user_id=user_id,
                mail_account_id=mail_account_id,
                email_domain=email_domain,
                is_enabled=True
            )
            db.add(config)
    except Exception as e:
        logger.warning(f"Phase Y Config konnte nicht erstellt werden: {type(e).__name__}")


# =============================================================================
# Route 13: /settings/mail-account/add (Zeile 6809-6939)
# =============================================================================
@accounts_bp.route("/settings/mail-account/add", methods=["GET", "POST"])
@login_required
def add_mail_account():
    """Fügt einen neuen Mail-Account hinzu (IMAP/SMTP)"""
    models = _get_models()
    encryption = _get_encryption()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return redirect(url_for("auth.login"))
            
            if request.method == "POST":
                # Input Validation
                name = request.form.get("name", "").strip()
                imap_server = request.form.get("imap_server", "").strip()
                imap_port = request.form.get("imap_port", "993")
                imap_username = request.form.get("imap_username", "").strip()
                imap_password = request.form.get("imap_password", "")
                imap_encryption = request.form.get("imap_encryption", "SSL")
                
                if not all([name, imap_server, imap_username, imap_password]):
                    return render_template(
                        "add_mail_account.html", 
                        error="Alle Felder sind erforderlich"
                    ), 400
                
                # Name Length Validation
                if len(name) > 100:
                    return render_template(
                        "add_mail_account.html",
                        error="Account-Name zu lang (max. 100 Zeichen)"
                    ), 400
                
                # Port Validation
                try:
                    imap_port = int(imap_port)
                    if not (1 <= imap_port <= 65535):
                        raise ValueError("Port außerhalb des gültigen Bereichs")
                except ValueError:
                    imap_port = 993
                
                # Master Key Check
                if not ensure_master_key_in_session():
                    return render_template(
                        "add_mail_account.html",
                        error="Session abgelaufen. Bitte neu einloggen."
                    ), 401
                
                master_key = session.get("master_key")
                
                try:
                    # Zero-Knowledge: Verschlüssele alle sensiblen Daten
                    encrypted_password = encryption.CredentialManager.encrypt_imap_password(
                        imap_password, master_key
                    )
                    encrypted_imap_server = encryption.CredentialManager.encrypt_server(
                        imap_server, master_key
                    )
                    encrypted_imap_username = encryption.CredentialManager.encrypt_email_address(
                        imap_username, master_key
                    )
                    
                    # Hash für Suche (nicht umkehrbar)
                    imap_server_hash = encryption.CredentialManager.hash_email_address(imap_server)
                    imap_username_hash = encryption.CredentialManager.hash_email_address(imap_username)
                except Exception as e:
                    logger.error(f"add_mail_account: Verschlüsselungsfehler: {type(e).__name__}: {e}")
                    return render_template(
                        "add_mail_account.html",
                        error="Fehler bei der Verschlüsselung"
                    ), 500
                
                # SMTP Felder (optional)
                smtp_server = request.form.get("smtp_server", "").strip() or None
                smtp_username = request.form.get("smtp_username", "").strip() or None
                
                encrypted_smtp_server = None
                encrypted_smtp_username = None
                
                if smtp_server:
                    try:
                        encrypted_smtp_server = encryption.CredentialManager.encrypt_server(
                            smtp_server, master_key
                        )
                    except Exception as e:
                        logger.warning(f"add_mail_account: SMTP-Server Verschlüsselung fehlgeschlagen: {type(e).__name__}")
                
                if smtp_username:
                    try:
                        encrypted_smtp_username = encryption.CredentialManager.encrypt_email_address(
                            smtp_username, master_key
                        )
                    except Exception as e:
                        logger.warning(f"add_mail_account: SMTP-Username Verschlüsselung fehlgeschlagen: {type(e).__name__}")
                
                # SMTP Port Validation
                try:
                    smtp_port = int(request.form.get("smtp_port", 587)) if smtp_server else None
                    if smtp_port and not (1 <= smtp_port <= 65535):
                        smtp_port = 587
                except (ValueError, TypeError):
                    smtp_port = 587 if smtp_server else None
                
                # Create Mail Account
                mail_account = models.MailAccount(
                    user_id=user.id,
                    name=name,
                    encrypted_imap_server=encrypted_imap_server,
                    imap_server_hash=imap_server_hash,
                    imap_port=imap_port,
                    encrypted_imap_username=encrypted_imap_username,
                    imap_username_hash=imap_username_hash,
                    encrypted_imap_password=encrypted_password,
                    imap_encryption=imap_encryption,
                    encrypted_smtp_server=encrypted_smtp_server,
                    smtp_port=smtp_port,
                    encrypted_smtp_username=encrypted_smtp_username,
                    smtp_encryption=request.form.get("smtp_encryption", "STARTTLS")
                )
                
                # SMTP Password (optional)
                smtp_password = request.form.get("smtp_password", "").strip()
                if smtp_password:
                    try:
                        encrypted_smtp_password = encryption.CredentialManager.encrypt_imap_password(
                            smtp_password, master_key
                        )
                        mail_account.encrypted_smtp_password = encrypted_smtp_password
                    except Exception as e:
                        logger.warning(f"add_mail_account: SMTP-Passwort Verschlüsselung fehlgeschlagen: {type(e).__name__}")
                
                db.add(mail_account)
                
                try:
                    db.commit()
                    
                    # Phase Y Config automatisch erstellen
                    email_domain = imap_username.split('@')[1] if '@' in imap_username else None
                    _initialize_phase_y_config(db, user.id, mail_account.id, email_domain)
                    
                    try:
                        db.commit()  # Commit Phase Y Config
                    except Exception:
                        pass  # Optional - ignorieren wenn fehlschlägt
                    
                    logger.info(f"✅ Mail-Account '{name}' hinzugefügt für User {user.username}")
                    flash(f"Mail-Account '{name}' erfolgreich hinzugefügt", "success")
                    return redirect(url_for("accounts.settings"))
                    
                except Exception as e:
                    db.rollback()
                    logger.error(f"add_mail_account: Commit-Fehler: {type(e).__name__}: {e}")
                    return render_template(
                        "add_mail_account.html",
                        error="Fehler beim Speichern des Accounts"
                    ), 500
            
            # GET: Zeige Formular
            return render_template("add_mail_account.html")
            
    except Exception as e:
        logger.error(f"add_mail_account: Fehler: {type(e).__name__}: {e}")
        return render_template(
            "add_mail_account.html",
            error="Unerwarteter Fehler"
        ), 500


# =============================================================================
# Route 14: /settings/mail-account/<id>/edit (Zeile 6941-7153)
# =============================================================================
@accounts_bp.route("/settings/mail-account/<int:account_id>/edit", methods=["GET", "POST"])
@login_required
def edit_mail_account(account_id):
    """Bearbeitet einen Mail-Account"""
    models = _get_models()
    encryption = _get_encryption()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return redirect(url_for("auth.login"))
            
            # Authorization Check
            account = db.query(models.MailAccount).filter_by(
                id=account_id, user_id=user.id
            ).first()
            
            if not account:
                flash("Account nicht gefunden", "danger")
                return redirect(url_for("accounts.settings"))
            
            if request.method == "POST":
                # Name Update
                new_name = request.form.get("name", "").strip()
                if new_name:
                    if len(new_name) > 100:
                        return render_template(
                            "edit_mail_account.html",
                            account=account,
                            error="Name zu lang (max. 100 Zeichen)"
                        ), 400
                    account.name = new_name
                
                # Port Update
                try:
                    account.imap_port = int(request.form.get("imap_port", account.imap_port))
                except (ValueError, TypeError):
                    pass
                
                account.imap_encryption = request.form.get("imap_encryption", account.imap_encryption)
                
                # Master Key Check
                if not ensure_master_key_in_session():
                    return render_template(
                        "edit_mail_account.html",
                        account=account,
                        error="Session abgelaufen. Bitte neu einloggen."
                    ), 401
                
                master_key = session.get("master_key")
                
                try:
                    # Zero-Knowledge: Verschlüssele Server und Username wenn geändert
                    new_imap_server = request.form.get("imap_server", "").strip()
                    if new_imap_server:
                        account.encrypted_imap_server = encryption.CredentialManager.encrypt_server(
                            new_imap_server, master_key
                        )
                        account.imap_server_hash = encryption.CredentialManager.hash_email_address(
                            new_imap_server
                        )
                    
                    new_imap_username = request.form.get("imap_username", "").strip()
                    if new_imap_username:
                        account.encrypted_imap_username = encryption.CredentialManager.encrypt_email_address(
                            new_imap_username, master_key
                        )
                        account.imap_username_hash = encryption.CredentialManager.hash_email_address(
                            new_imap_username
                        )
                    
                    new_password = request.form.get("imap_password", "").strip()
                    if new_password:
                        encrypted_password = encryption.CredentialManager.encrypt_imap_password(
                            new_password, master_key
                        )
                        account.encrypted_imap_password = encrypted_password
                    
                    # SMTP Felder
                    new_smtp_server = request.form.get("smtp_server", "").strip() or None
                    if new_smtp_server:
                        account.encrypted_smtp_server = encryption.CredentialManager.encrypt_server(
                            new_smtp_server, master_key
                        )
                    else:
                        account.encrypted_smtp_server = None
                    
                    try:
                        account.smtp_port = int(request.form.get("smtp_port", 587)) if new_smtp_server else None
                    except (ValueError, TypeError):
                        account.smtp_port = 587 if new_smtp_server else None
                    
                    new_smtp_username = request.form.get("smtp_username", "").strip() or None
                    if new_smtp_username:
                        account.encrypted_smtp_username = encryption.CredentialManager.encrypt_email_address(
                            new_smtp_username, master_key
                        )
                    else:
                        account.encrypted_smtp_username = None
                    
                    account.smtp_encryption = request.form.get("smtp_encryption", "STARTTLS")
                    
                    # SMTP Password
                    smtp_password = request.form.get("smtp_password", "").strip()
                    if smtp_password:
                        encrypted_smtp_password = encryption.CredentialManager.encrypt_imap_password(
                            smtp_password, master_key
                        )
                        account.encrypted_smtp_password = encrypted_smtp_password
                    
                    # Phase I.2: Account-spezifische Signatur
                    signature_enabled = request.form.get("signature_enabled") == "on"
                    account.signature_enabled = signature_enabled
                    
                    if signature_enabled:
                        signature_text = request.form.get("signature_text", "").strip()
                        if not signature_text:
                            return render_template(
                                "edit_mail_account.html",
                                account=account,
                                error="Signatur aktiviert aber Text ist leer. Bitte Text eingeben oder Checkbox deaktivieren."
                            ), 400
                        if len(signature_text) > 2000:
                            return render_template(
                                "edit_mail_account.html",
                                account=account,
                                error="Signatur zu lang (max. 2000 Zeichen)."
                            ), 400
                        
                        encrypted_signature = encryption.CredentialManager.encrypt_email_address(
                            signature_text, master_key
                        )
                        account.encrypted_signature_text = encrypted_signature
                    else:
                        account.encrypted_signature_text = None
                        
                except Exception as e:
                    logger.error(f"edit_mail_account: Verschlüsselungsfehler: {type(e).__name__}: {e}")
                    return render_template(
                        "edit_mail_account.html",
                        account=account,
                        error="Fehler bei der Verschlüsselung"
                    ), 500
                
                try:
                    db.commit()
                    logger.info(f"✅ Mail-Account '{account.name}' aktualisiert")
                    flash(f"Mail-Account '{account.name}' aktualisiert", "success")
                    return redirect(url_for("accounts.settings"))
                except Exception as e:
                    db.rollback()
                    logger.error(f"edit_mail_account: Commit-Fehler: {type(e).__name__}: {e}")
                    return render_template(
                        "edit_mail_account.html",
                        account=account,
                        error="Fehler beim Speichern"
                    ), 500
            
            # GET: Entschlüssele für Edit-Formular
            master_key = session.get("master_key")
            if master_key:
                try:
                    if account.encrypted_imap_server:
                        account.imap_server = encryption.CredentialManager.decrypt_server(
                            account.encrypted_imap_server, master_key
                        )
                    if account.encrypted_imap_username:
                        account.imap_username = encryption.CredentialManager.decrypt_email_address(
                            account.encrypted_imap_username, master_key
                        )
                    if account.encrypted_smtp_server:
                        account.smtp_server = encryption.CredentialManager.decrypt_server(
                            account.encrypted_smtp_server, master_key
                        )
                    if account.encrypted_smtp_username:
                        account.smtp_username = encryption.CredentialManager.decrypt_email_address(
                            account.encrypted_smtp_username, master_key
                        )
                    # Phase I.2: Entschlüssele Account-Signatur
                    if account.signature_enabled and account.encrypted_signature_text:
                        account.decrypted_signature_text = encryption.CredentialManager.decrypt_email_address(
                            account.encrypted_signature_text, master_key
                        )
                    else:
                        account.decrypted_signature_text = None
                except Exception as e:
                    logger.warning(f"edit_mail_account: Entschlüsselung fehlgeschlagen für Account {account.id}: {type(e).__name__}")
                    account.imap_server = "***verschlüsselt***"
                    account.imap_username = "***verschlüsselt***"
            
            return render_template("edit_mail_account.html", account=account)
            
    except Exception as e:
        logger.error(f"edit_mail_account: Fehler: {type(e).__name__}: {e}")
        flash("Fehler beim Bearbeiten des Accounts", "danger")
        return redirect(url_for("accounts.settings"))


@accounts_bp.route("/settings/mail-account/<int:account_id>/delete", methods=["POST"])
@login_required
def delete_mail_account(account_id):
    """Mail-Account löschen inkl. aller zugehörigen Emails"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                flash("Nicht authentifiziert", "danger")
                return redirect(url_for("auth.login"))
            
            account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
            if not account:
                flash("Account nicht gefunden", "danger")
                return redirect(url_for("accounts.settings"))
            
            account_name = account.name
            
            # Zuerst alle zugehörigen Emails löschen (FK-Constraint)
            try:
                raw_emails = db.query(models.RawEmail).filter_by(mail_account_id=account_id).all()
                deleted_count = 0
                
                for raw in raw_emails:
                    # Zuerst ProcessedEmail löschen (FK auf RawEmail)
                    processed = db.query(models.ProcessedEmail).filter_by(raw_email_id=raw.id).first()
                    if processed:
                        db.delete(processed)
                    db.delete(raw)
                    deleted_count += 1
                
                # Dann Account löschen
                db.delete(account)
                db.commit()
                
                logger.info(f"delete_mail_account: Account {account_id} ('{account_name}') gelöscht mit {deleted_count} Emails")
                flash(f"✅ Account '{account_name}' und {deleted_count} Emails gelöscht", "success")
                
            except Exception as e:
                db.rollback()
                logger.error(f"delete_mail_account: Commit-Fehler: {type(e).__name__}: {e}")
                flash("❌ Fehler beim Löschen des Accounts", "danger")
            
            return redirect(url_for("accounts.settings"))
    except Exception as e:
        logger.error(f"delete_mail_account: Fehler: {type(e).__name__}: {e}")
        flash("❌ Unerwarteter Fehler", "danger")
        return redirect(url_for("accounts.settings"))


@accounts_bp.route("/imap-diagnostics")
@login_required
def imap_diagnostics():
    """IMAP Diagnostics Dashboard"""
    return render_template("imap_diagnostics.html", csp_nonce=g.get("csp_nonce", ""))


@accounts_bp.route("/mail-account/<int:account_id>/fetch", methods=["POST"])
@login_required
def fetch_mails(account_id):
    """Triggert Background-Job für Mail-Fetch"""
    models = _get_models()
    
    try:
        # KRITISCH: Prüfen ob Account dem User gehört!
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Nicht authentifiziert"}), 401
            
            account = db.query(models.MailAccount).filter_by(
                id=account_id, user_id=user.id
            ).first()
            
            if not account:
                logger.warning(f"fetch_mails: User {user.id} versuchte Zugriff auf Account {account_id}")
                return jsonify({"error": "Account nicht gefunden"}), 404
        
        # Account gehört User - Job queuen
        job_queue = _get_job_queue()
        
        try:
            job_id = job_queue.enqueue_fetch(current_user.id, account_id)
            logger.info(f"fetch_mails: Job {job_id} für Account {account_id} gequeued")
            return jsonify({"job_id": job_id, "status": "queued"})
        except Exception as e:
            logger.error(f"fetch_mails: Queue-Fehler: {type(e).__name__}: {e}")
            return jsonify({"error": "Fehler beim Starten des Fetch-Jobs"}), 500
            
    except Exception as e:
        logger.error(f"fetch_mails: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@accounts_bp.route("/mail-account/<int:account_id>/purge", methods=["POST"])
@login_required
def purge_mail_account(account_id):
    """Löscht alle lokalen Emails eines Accounts - ATOMARE TRANSAKTION"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Nicht authentifiziert"}), 401
            
            # Authorization check
            account = db.query(models.MailAccount).filter_by(
                id=account_id, user_id=user.id
            ).first()
            
            if not account:
                logger.warning(f"purge_mail_account: User {user.id} versuchte Purge auf Account {account_id}")
                return jsonify({"error": "Account nicht gefunden"}), 404
            
            account_name = account.name
            
            try:
                # Zähle zuerst
                raw_emails = db.query(models.RawEmail).filter_by(mail_account_id=account_id).all()
                count = len(raw_emails)
                
                if count == 0:
                    return jsonify({"success": True, "deleted": 0, "message": "Keine Emails zum Löschen"})
                
                # Lösche in Transaktion
                for raw in raw_emails:
                    # Zuerst ProcessedEmail (FK)
                    processed = db.query(models.ProcessedEmail).filter_by(raw_email_id=raw.id).first()
                    if processed:
                        db.delete(processed)
                    db.delete(raw)
                
                db.commit()
                
                logger.info(f"purge_mail_account: {count} Emails für Account {account_id} ('{account_name}') gelöscht")
                return jsonify({"success": True, "deleted": count})
                
            except Exception as e:
                db.rollback()
                logger.error(f"purge_mail_account: Transaktion fehlgeschlagen: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Löschen - Transaktion zurückgerollt"}), 500
                
    except Exception as e:
        logger.error(f"purge_mail_account: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@accounts_bp.route("/jobs/<string:job_id>")
@login_required
def job_status(job_id):
    """Liefert Status-Infos zu einem Hintergrundjob"""
    # Validate job_id format (prevent injection)
    if not job_id or len(job_id) > 100:
        return jsonify({"error": "Ungültige Job-ID"}), 400
    
    try:
        job_queue = _get_job_queue()
        status = job_queue.get_status(job_id, current_user.id)
        if not status:
            return jsonify({"error": "Job nicht gefunden"}), 404
        return jsonify(status)
    except Exception as e:
        logger.error(f"job_status: Fehler für Job {job_id}: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@accounts_bp.route("/account/<int:account_id>/mail-count")
@login_required
def get_account_mail_count(account_id):
    """Zählt schnell wie viele Mails auf dem Server sind (ohne sie zu fetchen)
    
    Phase 13C Part 4: Quick Count für intelligentes Fetching
    - Zeigt User wie viele Mails remote vorhanden sind
    - User kann dann entscheiden: Alle holen oder in Portionen?
    
    Performance: Mit 30s Cache um doppelte Requests zu vermeiden
    """
    models = _get_models()
    encryption = _get_encryption()
    mail_fetcher = _get_mail_fetcher()
    
    current_time = time.time()
    cache_key = account_id
    
    # Cache-Check: Verwende gecachte Daten wenn < 30s alt
    if cache_key in _mail_count_cache:
        cache_entry = _mail_count_cache[cache_key]
        cache_age = current_time - _mail_count_cache_time.get(cache_key, 0)
        if cache_age < MAIL_COUNT_CACHE_TTL:
            logger.info(f"⚡ Cache-Hit für Account {account_id} (Alter: {cache_age:.1f}s)")
            return jsonify(cache_entry)
    
    # Optional: since_date für SINCE count (Format: YYYY-MM-DD)
    since_date_str = request.args.get('since_date')
    since_date = None
    if since_date_str:
        try:
            from datetime import datetime
            since_date = datetime.strptime(since_date_str, '%Y-%m-%d')
        except ValueError:
            logger.warning(f"Ungültiges since_date Format: {since_date_str}")
            since_date = None
    
    # Optional: unseen_only für kombinierte Filter
    unseen_only = request.args.get('unseen_only', '').lower() == 'true'
    
    # include_folders als JSON-Array
    include_folders_param = request.args.get('include_folders')
    include_folders_set = None
    if include_folders_param:
        try:
            include_folders_list = json.loads(include_folders_param)
            include_folders_set = set(include_folders_list) if include_folders_list else None
            logger.info(f"🎯 SINCE-Search nur für {len(include_folders_set)} Include-Ordner")
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Ungültiges include_folders Format: {e}")
            include_folders_set = None
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Nicht authentifiziert"}), 401
            
            account = db.query(models.MailAccount).filter_by(
                id=account_id, user_id=user.id
            ).first()
            
            if not account:
                return jsonify({"error": "Account nicht gefunden"}), 404
            
            if account.auth_type != "imap":
                return jsonify({"error": "IMAP-Account erforderlich"}), 400
            
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master-Key erforderlich"}), 401
            
            try:
                imap_server = encryption.CredentialManager.decrypt_server(
                    account.encrypted_imap_server, master_key
                )
                imap_username = encryption.CredentialManager.decrypt_email_address(
                    account.encrypted_imap_username, master_key
                )
                imap_password = encryption.CredentialManager.decrypt_imap_password(
                    account.encrypted_imap_password, master_key
                )
            except Exception as e:
                logger.error(f"get_account_mail_count: Entschlüsselungsfehler: {type(e).__name__}")
                return jsonify({"error": "Entschlüsselung fehlgeschlagen"}), 500
            
            fetcher = mail_fetcher.MailFetcher(
                server=imap_server,
                username=imap_username,
                password=imap_password,
                port=account.imap_port
            )
            
            try:
                fetcher.connect()
                
                # IMAPClient.list_folders() gibt Tupel zurück
                folders = fetcher.connection.list_folders()
                
                folder_counts = {}
                total_remote = 0
                total_unseen = 0
                
                for flags, delimiter, folder_name in folders:
                    # folder_name ist bytes, decode UTF-7
                    folder_display = mail_fetcher.decode_imap_folder_name(folder_name)
                    
                    # Prüfe ob Folder selectable ist
                    if b'\\Noselect' in flags or '\\Noselect' in [f.decode() if isinstance(f, bytes) else f for f in flags]:
                        continue
                    
                    try:
                        # Status gibt direkt Dict zurück
                        status_dict = fetcher.connection.folder_status(folder_name, ['MESSAGES', 'UNSEEN'])
                        
                        messages_count = status_dict.get(b'MESSAGES', 0)
                        unseen_count = status_dict.get(b'UNSEEN', 0)
                        
                        # SINCE-Search nur für include_folders
                        since_count = None
                        if since_date and include_folders_set is not None:
                            if folder_display in include_folders_set:
                                try:
                                    fetcher.connection.select_folder(folder_name, readonly=True)
                                    date_str = since_date.strftime("%d-%b-%Y")
                                    
                                    search_criteria = ['SINCE', date_str]
                                    if unseen_only:
                                        search_criteria.append('UNSEEN')
                                    
                                    since_messages = fetcher.connection.search(search_criteria)
                                    since_count = len(since_messages) if since_messages else 0
                                except Exception as search_err:
                                    logger.debug(f"SINCE search failed für {folder_display}: {search_err}")
                                    since_count = None
                        
                        folder_counts[folder_display] = {
                            "total": messages_count,
                            "unseen": unseen_count,
                            "since": since_count
                        }
                        total_remote += messages_count
                        total_unseen += unseen_count
                    except Exception as e:
                        logger.warning(f"Status fehlgeschlagen für {folder_display}: {e}")
                        continue
                
                # Zähle lokale Mails in DB
                total_local = db.query(models.RawEmail).filter(
                    models.RawEmail.mail_account_id == account_id,
                    models.RawEmail.deleted_at.is_(None)
                ).count()
                
                result_data = {
                    "account_id": account_id,
                    "folders": folder_counts,
                    "summary": {
                        "total_remote": total_remote,
                        "total_unseen": total_unseen,
                        "total_local": total_local,
                        "delta": total_remote - total_local
                    }
                }
                
                # Cache speichern
                _mail_count_cache[cache_key] = result_data
                _mail_count_cache_time[cache_key] = current_time
                logger.info(f"💾 Cache gespeichert für Account {account_id}")
                
                return jsonify(result_data)
                
            finally:
                try:
                    fetcher.disconnect()
                except Exception:
                    pass
                    
    except Exception as e:
        logger.error(f"get_account_mail_count: Fehler für Account {account_id}: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@accounts_bp.route("/account/<int:account_id>/folders")
@login_required
def get_account_folders(account_id):
    """Listet verfügbare Ordner für einen IMAP-Account auf"""
    models = _get_models()
    encryption = _get_encryption()
    mail_fetcher = _get_mail_fetcher()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Nicht authentifiziert"}), 401
            
            account = db.query(models.MailAccount).filter_by(
                id=account_id, user_id=user.id
            ).first()
            
            if not account:
                return jsonify({"error": "Account nicht gefunden"}), 404
            
            if account.auth_type != "imap":
                return jsonify({"error": "IMAP-Account erforderlich"}), 400
            
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master-Key erforderlich"}), 401
            
            try:
                imap_server = encryption.CredentialManager.decrypt_server(
                    account.encrypted_imap_server, master_key
                )
                imap_username = encryption.CredentialManager.decrypt_email_address(
                    account.encrypted_imap_username, master_key
                )
                imap_password = encryption.CredentialManager.decrypt_imap_password(
                    account.encrypted_imap_password, master_key
                )
            except Exception as e:
                logger.error(f"get_account_folders: Entschlüsselungsfehler: {type(e).__name__}")
                return jsonify({"error": "Entschlüsselung fehlgeschlagen"}), 500
            
            fetcher = mail_fetcher.MailFetcher(
                server=imap_server,
                username=imap_username,
                password=imap_password,
                port=account.imap_port
            )
            
            try:
                fetcher.connect()
                
                if not fetcher.connection:
                    logger.error(f"IMAP-Verbindung nicht initialisiert für Account {account_id}")
                    return jsonify({"error": "IMAP-Verbindung fehlgeschlagen"}), 500
                
                # IMAPClient.list_folders() returns (flags, delimiter, folder_name) tuples
                mailboxes = fetcher.connection.list_folders()
                
                folders = []
                for flags, delimiter, folder_name in mailboxes:
                    # Skip \Noselect folders
                    if b'\\Noselect' in flags or '\\Noselect' in [f.decode() if isinstance(f, bytes) else f for f in flags]:
                        continue
                    # folder_name is bytes, decode UTF-7
                    folder_display = mail_fetcher.decode_imap_folder_name(folder_name)
                    folders.append({"name": folder_display})
                
                folders.sort(key=lambda x: x['name'])
                return jsonify({"success": True, "folders": folders})
                
            except Exception as e:
                logger.error(f"get_account_folders: IMAP-Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "IMAP-Abfrage fehlgeschlagen"}), 500
            finally:
                try:
                    fetcher.disconnect()
                except Exception:
                    pass
                    
    except Exception as e:
        logger.error(f"get_account_folders: Fehler für Account {account_id}: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@accounts_bp.route("/whitelist-imap-setup")
@login_required
def whitelist_imap_setup_page():
    """Bulk-Whitelist via IMAP-Scan"""
    return render_template("whitelist_imap_setup.html", csp_nonce=g.get("csp_nonce", ""))
